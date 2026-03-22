"""
차량 음성비서 개인화 시스템 - L2 Event Log 모델 정의

L2 Layer는 L1(Raw 대화 로그)을 세션 단위로 분석하여
정형화된 이벤트로 변환한 결과를 저장합니다.

파이프라인:
    L1 (Raw 대화) → LLM 추출 → L2 (Event Log) → 패턴 분석 → L3 (Core Profile)

이 모듈은 L2 Event Log의 데이터 모델을 정의합니다.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


# ============================================================================
# Enums
# ============================================================================

class TriggerType(str, Enum):
    """
    이벤트가 누구에 의해 시작되었는지를 나타냅니다.

    개인화 평가에서 가장 중요한 축 중 하나입니다.
    시스템이 먼저 제안(proactive)해서 유저가 수락한 비율이
    개인화 성숙도의 핵심 지표(Proactive Ratio)가 됩니다.
    """

    USER_INITIATED = "user_initiated"
    """
    유저가 먼저 요청한 경우.

    예시:
        - 유저: "스타벅스 가줘"
        - 유저: "에어컨 23도로 해줘"
        - 유저: "뉴스 틀어줘"

    이 경우 user_response는 항상 null입니다.
    유저가 스스로 요청했으므로 수락/거부 개념이 없습니다.
    """

    PROACTIVE = "proactive"
    """
    시스템(AI)이 먼저 제안한 경우.
    L3 패턴 매칭 결과로 시스템이 선제적으로 제안한 것입니다.

    예시:
        - AI: "회사로 안내할까요?" (출퇴근 패턴 기반)
        - AI: "재즈 플레이리스트를 재생할까요?" (음악 선호 기반)
        - AI: "에어컨 23도로 설정할까요?" (온도 선호 기반)

    이 경우 반드시 user_response가 함께 기록되어야 합니다.
    user_response가 null이면 데이터 품질 문제입니다.

    연결 필드:
        - pattern_id: 어떤 L3 패턴에 의해 제안되었는지
        - user_response: 유저가 이 제안을 어떻게 받아들였는지
    """


class UserResponse(str, Enum):
    """
    시스템의 선제적 제안(proactive)에 대한 유저의 반응.

    trigger_type이 "proactive"일 때만 유의미합니다.
    trigger_type이 "user_initiated"이면 이 값은 null이어야 합니다.

    이 값은 L3 패턴의 신뢰도 갱신과 개인화 평가지표(수락률)의
    핵심 데이터입니다.
    """

    ACCEPTED = "accepted"
    """
    제안을 그대로 수락한 경우.

    예시:
        - AI: "회사로 안내할까요?" → 유저: "응"
        - AI: "회사로 안내할까요?" → 유저: "가자"
        - AI: "에어컨 23도로 할까요?" → (유저가 별다른 말 없이 수용)

    수락률(Acceptance Rate) = accepted / (accepted + rejected + modified + ignored)
    이 지표가 개인화 품질의 1차 평가 기준입니다.
    """

    REJECTED = "rejected"
    """
    제안을 거부하고 완전히 다른 것을 요청한 경우.

    예시:
        - AI: "회사로 안내할까요?" → 유저: "아니 오늘은 병원 가야해"
        - AI: "재즈 플레이리스트를 재생할까요?" → 유저: "아니 발라드로"

    rejected가 반복되면 해당 L3 패턴의 confidence를 낮추거나
    패턴 자체를 decay 처리해야 합니다.

    중요: rejected 이벤트의 resolved_params에는 유저가 최종 요청한
    파라미터(예: "병원", "발라드")가 기록됩니다. 이 데이터는
    기존 패턴 수정 또는 새로운 패턴 생성의 근거가 됩니다.
    """

    MODIFIED = "modified"
    """
    제안을 부분적으로 수정한 경우.
    제안의 방향은 맞지만 세부사항을 변경한 것입니다.

    예시:
        - AI: "회사로 안내할까요?" → 유저: "응, 근데 고속도로 말고"
            → domain/action은 수락, route_preference만 변경
        - AI: "에어컨 23도로 할까요?" → 유저: "24도로 해줘"
            → action은 수락, temperature만 변경

    modified는 패턴 자체는 유효하지만 파라미터 조정이 필요하다는
    시그널입니다. L3 패턴의 suggested_params를 업데이트하는
    근거로 사용됩니다.
    """

    IGNORED = "ignored"
    """
    시스템이 제안했으나 유저가 아무런 반응을 하지 않은 경우.

    예시:
        - AI: "회사로 안내할까요?" → (5초 이상 무응답)
        - AI: "뉴스를 틀어드릴까요?" → 유저가 완전히 다른 주제로 대화

    판단 기준:
        - 제안 후 일정 시간(예: 10초) 내 해당 domain 관련 응답 없음
        - 제안 후 유저가 완전히 다른 domain으로 발화

    ignored는 rejected보다 약한 부정 시그널입니다.
    유저가 못 들었을 수도, 타이밍이 안 맞았을 수도 있습니다.
    반복되면 해당 조건에서의 제안 빈도를 줄이는 근거가 됩니다.
    """


# ============================================================================
# Core Models
# ============================================================================

class ResolvedParams(BaseModel):
    """
    이벤트에서 추출된 구체적 파라미터.

    유저의 발화에서 실제로 의도한 구체적인 값을 정규화한 것입니다.
    모든 값은 taxonomy에 정의된 허용값(enum) 또는 허용 타입(number, text)
    범위 내에서만 기록됩니다.

    이 필드가 L2의 핵심 가치입니다.
    L1에는 자연어("스벅 가자", "에어컨 좀 세게")만 있고,
    L2에서 이를 정규화된 파라미터로 변환합니다.

    예시 (domain/action별):

        navigation/route_guidance:
            {
                "destination_category": "cafe",      # taxonomy enum
                "destination_name": "스타벅스 강남역점", # 자유 텍스트
                "route_preference": "highway_avoid"   # taxonomy enum
            }

        climate/set_temperature:
            {
                "temperature": 23,     # number
                "zone": "all"          # taxonomy enum: driver | passenger | all
            }

        media/music_play:
            {
                "genre": "ballad",     # taxonomy enum
                "source": "melon"      # taxonomy enum
            }

        media/news_play:
            {
                "news_category": "경제"  # taxonomy enum
            }

        phone/call:
            {
                "contact_relation": "family",  # taxonomy enum
                "contact_label": "엄마"         # 자유 텍스트 (유저가 부른 호칭)
            }

    중요:
        - 수정이 있었을 경우 '최종 확정된 값'만 기록합니다.
          예) "뉴스 틀어줘" → "경제뉴스로" → news_category: "경제" (최종값)
        - trigger_type이 proactive이고 user_response가 rejected인 경우,
          유저가 대신 요청한 값이 기록됩니다.
          예) AI가 "재즈" 제안 → 유저 "발라드로" → genre: "ballad"
        - taxonomy에 정의되지 않은 값은 "other"로 기록하고,
          원본 텍스트는 raw_utterances에서 확인할 수 있습니다.
    """

    model_config = {"extra": "allow"}  # domain/action별로 필드가 다르므로


class EventLog(BaseModel):
    """
    L2 Layer의 핵심 데이터 모델.

    하나의 EventLog는 유저의 '하나의 완결된 의도(intent)'를 나타냅니다.
    L1의 여러 대화 턴이 하나의 EventLog로 묶일 수 있습니다.

    예시: 아래 3개의 L1 메시지가 1개의 EventLog가 됩니다.
        - 유저: "뉴스 틀어줘"
        - AI:   "오늘의 주요 뉴스를 재생합니다."
        - 유저: "이거 말고 경제뉴스"
        - AI:   "경제 뉴스로 변경합니다."
        → EventLog(domain="media", action="news_play",
                    resolved_params={"news_category": "경제"},
                    turns_to_complete=2)

    생명주기:
        1. L1에 세션 대화 원문이 저장됨 (실시간, 매 발화)
        2. 세션 종료 시 L2 Preprocessor가 L1 대화를 조회
        3. LLM이 대화 맥락을 분석하여 EventLog 목록을 추출
        4. Pydantic 검증 후 event_logs 테이블에 저장
        5. Daily/Weekly 배치에서 event_logs → L3 패턴/프로필 생성

    활용:
        - 개인화 평가지표 산출 (수락률, 선제비율, 턴 감소율)
        - L3 패턴 감지의 입력 데이터
        - 관리자 대시보드 (도메인/액션별 통계)
        - 미분류(unclassified) 발화 리뷰
    """

    # ────────────────────────────────────────────────────────────
    # 식별 필드
    # ────────────────────────────────────────────────────────────

    event_index: int = Field(
        description=(
            "세션 내 이벤트 순서 (0부터 시작). "
            "하나의 세션에서 추출된 이벤트들의 시간순 인덱스입니다. "
            "이벤트 간 시퀀스 패턴 분석에 사용됩니다. "
            "예: event_index 0(네비) → 1(에어컨) → 2(뉴스)가 반복되면 "
            "'출근 시퀀스' 패턴으로 감지할 수 있습니다."
        ),
        examples=[0, 1, 2],
    )

    start_utterance_ts: datetime = Field(
        description=(
            "이 이벤트의 첫 번째 관련 발화 시각. "
            "trigger_type이 proactive이면 AI의 제안 발화 시각, "
            "user_initiated이면 유저의 요청 발화 시각입니다. "
            "L3 패턴의 시간 조건(hour_range, day_of_week) 매칭과 "
            "이벤트 간 시간 간격 분석에 사용됩니다."
        ),
        examples=["2026-03-22T08:30:15"],
    )

    # ────────────────────────────────────────────────────────────
    # 분류 필드 (Chat Service의 Domain/Action과 동일 체계)
    # ────────────────────────────────────────────────────────────

    domain: str = Field(
        description=(
            "이벤트의 1차 분류 (도메인). "
            "Chat Service의 intent 분류에서 이미 확정된 값을 그대로 사용합니다. "
            "taxonomy_domains 테이블의 key와 일치해야 합니다. "
            "\n\n"
            "예시 도메인:\n"
            "  - navigation: 목적지 안내, 장소 검색, 경로 관련\n"
            "  - climate: 에어컨, 히터, 환기, 시트 온도\n"
            "  - media: 음악, 뉴스, 라디오, 팟캐스트, 볼륨\n"
            "  - vehicle: 창문, 선루프, 트렁크, 와이퍼, 조명\n"
            "  - phone: 전화, 문자 읽기/전송\n"
            "\n"
            "L3 패턴 분석에서 가장 상위 그룹핑 단위입니다. "
            "도메인별 수락률, 선제비율을 산출하여 "
            "어떤 영역의 개인화가 잘 되고 있는지 평가합니다."
        ),
        examples=["navigation", "climate", "media", "vehicle", "phone"],
    )

    action: str = Field(
        description=(
            "이벤트의 2차 분류 (도메인 내 구체적 인텐트). "
            "Chat Service의 intent 분류에서 이미 확정된 값을 그대로 사용합니다. "
            "taxonomy_categories 테이블의 key와 일치해야 하며, "
            "해당 domain에 속한 action만 허용됩니다. "
            "\n\n"
            "예시 (domain별):\n"
            "  - navigation: route_guidance, search_place, cancel_navigation\n"
            "  - climate: set_temperature, fan_control, ventilation, heated_seat\n"
            "  - media: music_play, news_play, radio_play, volume_control\n"
            "  - vehicle: window_open, window_close, sunroof, trunk\n"
            "  - phone: call, message_read, message_send\n"
            "\n"
            "domain + action 조합이 L3 패턴의 suggested_domain + suggested_action과 "
            "매칭되어 제안 정확도를 평가합니다."
        ),
        examples=["route_guidance", "set_temperature", "music_play", "call"],
    )

    # ────────────────────────────────────────────────────────────
    # 파라미터 (taxonomy 확장에 의해 정의됨)
    # ────────────────────────────────────────────────────────────

    resolved_params: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "이벤트에서 추출된 정규화된 파라미터. "
            "자연어 발화에서 LLM이 추출하여 taxonomy에 정의된 허용값으로 매핑한 결과입니다. "
            "\n\n"
            "핵심 규칙:\n"
            "  1. 대화 중 수정이 있었을 경우 '최종 확정값'만 기록\n"
            "     예) '뉴스 틀어줘' → '경제뉴스로' → {news_category: '경제'}\n"
            "  2. taxonomy enum에 없는 값은 'other'로 기록\n"
            "  3. trigger_type=proactive이고 user_response=rejected인 경우,\n"
            "     유저가 대신 요청한 값이 기록됨\n"
            "     예) AI 제안 '재즈' → 유저 '발라드로' → {genre: 'ballad'}\n"
            "\n"
            "예시:\n"
            "  navigation/route_guidance:\n"
            "    {destination_category: 'work', route_preference: 'fastest'}\n"
            "  climate/set_temperature:\n"
            "    {temperature: 23, zone: 'all'}\n"
            "  media/music_play:\n"
            "    {genre: 'ballad', source: 'melon'}\n"
            "\n"
            "이 필드가 L3 프로필(선호 온도, 선호 장르 등) 생성의 핵심 데이터입니다. "
            "SQL GROUP BY로 최빈값을 집계하거나, LLM 배치로 복합 조건을 분석합니다."
        ),
    )

    # ────────────────────────────────────────────────────────────
    # 제안/반응 필드 (개인화 평가의 핵심)
    # ────────────────────────────────────────────────────────────

    trigger_type: TriggerType = Field(
        description=(
            "이벤트의 시작 주체. "
            "개인화 시스템의 성숙도를 측정하는 가장 중요한 축입니다. "
            "\n\n"
            "측정 지표:\n"
            "  Proactive Ratio = proactive 중 accepted / 전체 이벤트\n"
            "  초기 유저: ~0.0 (모든 요청이 user_initiated)\n"
            "  학습 완료: ~0.5+ (절반 이상 시스템이 먼저 제안)\n"
            "\n"
            "판단 기준:\n"
            "  - AI가 먼저 '~할까요?'로 제안 → proactive\n"
            "  - 유저가 먼저 '~해줘'로 요청 → user_initiated\n"
            "  - AI가 정보 제공 후 유저가 선택 → user_initiated\n"
            "    (AI가 옵션을 나열한 것은 제안이 아님)"
        ),
        examples=["user_initiated", "proactive"],
    )

    pattern_id: str | None = Field(
        default=None,
        description=(
            "이 제안이 어떤 L3 패턴에 의해 트리거되었는지. "
            "trigger_type이 proactive일 때만 값이 있습니다. "
            "l3_patterns 테이블의 id를 참조합니다. "
            "\n\n"
            "용도:\n"
            "  - 패턴별 수락률 추적: 이 pattern_id로 GROUP BY하여\n"
            "    각 패턴의 성공률을 개별 측정\n"
            "  - 패턴 decay 판단: 특정 패턴의 rejected/ignored가\n"
            "    연속 N회 이상이면 confidence 하향\n"
            "  - 디버깅: 왜 이 제안이 나왔는지 역추적\n"
            "\n"
            "trigger_type이 user_initiated이면 반드시 null이어야 합니다."
        ),
        examples=["weekday_commute_001", "evening_jazz_015", None],
    )

    user_response: UserResponse | None = Field(
        default=None,
        description=(
            "시스템 제안에 대한 유저의 반응. "
            "trigger_type이 proactive일 때만 유의미하며, "
            "user_initiated이면 null이어야 합니다. "
            "\n\n"
            "L3 패턴 피드백 루프:\n"
            "  accepted → pattern confidence 유지/상승\n"
            "  modified → pattern params 조정 필요\n"
            "  rejected → pattern confidence 하락, 대안 패턴 학습\n"
            "  ignored  → 약한 부정 시그널, 반복 시 제안 빈도 감소\n"
            "\n"
            "데이터 정합성 규칙:\n"
            "  - trigger_type=proactive → user_response는 not null\n"
            "  - trigger_type=user_initiated → user_response는 null\n"
            "  위반 시 데이터 품질 경고를 발생시켜야 합니다."
        ),
        examples=["accepted", "rejected", "modified", "ignored", None],
    )

    # ────────────────────────────────────────────────────────────
    # 효율성 지표
    # ────────────────────────────────────────────────────────────

    turns_to_complete: int = Field(
        description=(
            "이 의도를 완료하는 데 필요한 유저 발화 수. "
            "의도 시작부터 완료(Agent가 최종 실행)까지 유저가 말한 횟수입니다. "
            "AI 발화는 카운트하지 않습니다. "
            "\n\n"
            "예시:\n"
            "  - '스타벅스 가줘' → 바로 안내 → turns: 1\n"
            "  - '뉴스 틀어줘' → '경제뉴스로' → turns: 2\n"
            "  - '음악 틀어줘' → 'AI: 재즈?' → '아니 발라드' → turns: 2\n"
            "  - '근처 맛집' → 'AI: 3곳 추천' → '두번째로' → turns: 2\n"
            "\n"
            "개인화 평가 지표 - 턴 감소율:\n"
            "  Turn Reduction = (초기 평균 턴 - 현재 평균 턴) / 초기 평균 턴\n"
            "  개인화가 잘 되면 시스템이 유저 의도를 바로 파악하므로\n"
            "  같은 domain/action의 평균 턴 수가 시간이 지남에 따라 감소합니다.\n"
            "\n"
            "주의: turns_to_complete가 1이 아닌 이벤트는 \n"
            "resolved_params에 수정 과정이 반영되어 있어야 합니다."
        ),
        ge=1,
        examples=[1, 2, 3],
    )

    # ────────────────────────────────────────────────────────────
    # 원본 참조 (디버깅/감사용)
    # ────────────────────────────────────────────────────────────

    raw_utterances: list[str] = Field(
        default_factory=list,
        description=(
            "이 이벤트에 관련된 원본 발화 목록. "
            "유저 발화와 AI 발화를 시간순으로 모두 포함합니다. "
            "\n\n"
            "용도:\n"
            "  - LLM 추출 결과 검증: resolved_params가 원문과 일치하는지 확인\n"
            "  - 미분류(unclassified) 분석: 왜 분류에 실패했는지 원문 확인\n"
            "  - 택소노미 개선: 새로운 카테고리가 필요한지 판단할 때 원문 참고\n"
            "  - 감사(audit): 개인정보 관련 이슈 발생 시 원본 대화 추적\n"
            "\n"
            "예시:\n"
            "  turns_to_complete=1인 경우:\n"
            "    ['스타벅스 가줘', '강남역 스타벅스로 안내합니다.']\n"
            "  turns_to_complete=2인 경우:\n"
            "    ['뉴스 틀어줘', '오늘의 주요 뉴스를 재생합니다.',\n"
            "     '이거 말고 경제뉴스', '경제 뉴스로 변경합니다.']\n"
            "\n"
            "주의: 이 필드는 디버깅/감사 목적이며, "
            "패턴 분석에는 사용하지 않습니다. "
            "패턴 분석은 반드시 정규화된 domain/action/resolved_params를 사용하세요."
        ),
    )

    # ────────────────────────────────────────────────────────────
    # Validators
    # ────────────────────────────────────────────────────────────

    @model_validator(mode="after")
    def validate_trigger_response_consistency(self) -> "EventLog":
        """
        trigger_type과 user_response의 정합성을 검증합니다.

        규칙:
            - proactive 이벤트는 반드시 user_response가 있어야 합니다.
            - user_initiated 이벤트는 user_response가 null이어야 합니다.
            - proactive 이벤트는 pattern_id가 있어야 합니다. (권장, 경고만)
        """
        if self.trigger_type == TriggerType.PROACTIVE and self.user_response is None:
            raise ValueError(
                "trigger_type이 'proactive'인 이벤트는 "
                "user_response가 반드시 있어야 합니다. "
                "유저가 제안에 어떻게 반응했는지 기록되지 않으면 "
                "개인화 평가가 불가능합니다."
            )

        if self.trigger_type == TriggerType.USER_INITIATED and self.user_response is not None:
            raise ValueError(
                "trigger_type이 'user_initiated'인 이벤트는 "
                "user_response가 null이어야 합니다. "
                "유저가 스스로 요청한 것에 수락/거부 개념은 없습니다."
            )

        return self

    @model_validator(mode="after")
    def validate_turns_and_utterances(self) -> "EventLog":
        """
        turns_to_complete와 raw_utterances의 정합성을 검증합니다.

        raw_utterances에는 유저+AI 발화가 모두 포함되므로,
        최소 turns_to_complete 이상의 유저 발화가 있어야 합니다.
        """
        if self.raw_utterances:
            # raw_utterances가 있으면 최소 turns * 2 (유저+AI 쌍) 정도는 있어야
            min_expected = self.turns_to_complete * 2
            if len(self.raw_utterances) < self.turns_to_complete:
                raise ValueError(
                    f"turns_to_complete={self.turns_to_complete}이지만 "
                    f"raw_utterances가 {len(self.raw_utterances)}개뿐입니다. "
                    f"최소 {self.turns_to_complete}개의 발화가 있어야 합니다."
                )

        return self


# ============================================================================
# LLM 추출 결과 래퍼
# ============================================================================

class SessionSummary(BaseModel):
    """
    세션 전체의 요약 정보.

    이벤트 추출과 함께 생성되며, 세션 레벨 통계에 사용됩니다.
    """

    start_time: datetime = Field(
        description="세션 첫 메시지 시각 (AI 또는 유저 중 먼저 발화한 시점)",
    )

    end_time: datetime = Field(
        description="세션 마지막 메시지 시각",
    )

    total_user_turns: int = Field(
        description=(
            "세션 내 유저 발화 총 수. "
            "전체 events의 turns_to_complete 합과 같거나 커야 합니다. "
            "(일부 발화가 이벤트로 분류되지 않을 수 있으므로)"
        ),
        ge=1,
    )


class ExtractionResult(BaseModel):
    """
    L2 Preprocessor가 LLM으로부터 받는 최종 결과물.

    하나의 세션(트립)에 대한 전체 추출 결과입니다.
    이 결과가 검증을 통과하면 event_logs 테이블에 저장됩니다.
    """

    session_id: str = Field(
        description=(
            "L1의 session_id와 동일. "
            "L1 ↔ L2 간 데이터 연결에 사용됩니다."
        ),
    )

    session_summary: SessionSummary = Field(
        description="세션 전체 요약 정보",
    )

    events: list[EventLog] = Field(
        description=(
            "추출된 이벤트 목록. event_index 순으로 정렬되어야 합니다. "
            "하나의 세션에서 0개 이상의 이벤트가 추출될 수 있습니다. "
            "0개인 경우는 유저가 시동만 걸고 아무 요청도 하지 않은 경우입니다."
        ),
    )

    unclassified: list[dict] = Field(
        default_factory=list,
        description=(
            "taxonomy에 매핑되지 않은 발화 목록. "
            "관리자 리뷰 대상이며, 택소노미 확장의 근거가 됩니다. "
            "\n\n"
            "구조:\n"
            "  [{'utterance': '원본 발화', 'reason': '분류 실패 사유'}]\n"
            "\n"
            "예시:\n"
            "  {'utterance': '주가 어때', 'reason': '금융 도메인 미정의'}\n"
            "  {'utterance': '오늘 미세먼지', 'reason': '날씨 도메인 미정의'}\n"
            "\n"
            "주간 리뷰에서 빈도순으로 정렬하여, "
            "상위 항목에 대해 택소노미 추가 여부를 결정합니다."
        ),
    )

    @model_validator(mode="after")
    def validate_event_indices(self) -> "ExtractionResult":
        """event_index가 0부터 순차적인지 검증합니다."""
        indices = [e.event_index for e in self.events]
        expected = list(range(len(self.events)))
        if indices != expected:
            raise ValueError(
                f"event_index가 순차적이지 않습니다: {indices}, "
                f"expected: {expected}"
            )
        return self