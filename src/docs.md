


# 아래내용을 반드시 최소한의 형태로 구현하세요. 코드를 깔끔하고 명확하게 작성하세요.

- 장기기억 수립 전략 
메모리 계층화
L1(daily) -> 단일 요청시 Human,AI Message 쌍을 저장하는 레이어,(일별 모든 대화를 수집)
L2(weekly) -> 주간별로 사용자의 패턴을 분석(L1 데이터를 활용)
  - MemoryBank 알고리즘을 적용할계획임, 하지만 현재 구현사항에서는 패스(여러 알고리즘이 적용가능한 형태로 프로토타입제작)
L3(monthly) -> 월별로 사용자의 패턴을 분석 (L2 데이터를 활용)





API 구현
(backend) - (memory)
- 핵심사항
  - backend 서버에서 대화를 저장할때 memory 서버를 호출하고 memory 서버는 즉시 응답반환(201 Created)
  -memory 서버는 업데이트시에도 기존 작업은 완료하고 배포되어야함(gracefull shutdown 지원)



사용기술 

L1,L2,L3 모두 mongodb 를 사용 / GraphDB는 L3에서 사용할지 생각 




apis (api 폴더)
core (db 등 핵심 모듈)
layers (l1,l2,l3 layer를 담당하는 storage)
models (실제 db모델과 소통하는 schema)
schemas (in & out을 담당할 schema)
main.py (메인 실행함수)













폴더 : /Users/jeonjaehyeon/Desktop/개발/projects/ai_project/memory/src


