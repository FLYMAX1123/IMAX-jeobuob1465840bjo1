from curl_cffi import requests

print("CGV 광교 IMAX 알리미 테스트 시작!")

response = requests.get(
    "https://cgv.co.kr/cnm/movieBook",
    impersonate="chrome",
    timeout=30
)

print("CGV 접속 상태:", response.status_code)

if response.status_code == 200:
    print("정상적으로 실행되었습니다!")
else:
    print("접속에 실패했습니다.")
