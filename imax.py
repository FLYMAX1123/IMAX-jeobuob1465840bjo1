import os
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from curl_cffi import requests

THEATER_NAME = "CGV 광교"
THEATER_CODE = "0257"
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
STATE_FILE = "last_imax.json"

BOOKING_PAGE = "https://cgv.co.kr/cnm/movieBook"
API_URL = "https://cgv.co.kr/api/v1/booking/searchMovScnInfo"

KST = ZoneInfo("Asia/Seoul")


def get_imax_schedules():
    print("=" * 40)
    print("CGV 광교 IMAX 확인 시작")
    print("=" * 40)

    session = requests.Session(impersonate="chrome")

    response = session.get(
        BOOKING_PAGE,
        timeout=30
    )

    print("CGV 접속 상태:", response.status_code)

    if response.status_code != 200:
        raise Exception(f"CGV 접속 실패: {response.status_code}")

    imax_list = []

    # 한국 시간 기준 오늘
    today = datetime.now(KST).date()

    for i in range(14):
        target_date = today + timedelta(days=i)
        date_text = target_date.strftime("%Y%m%d")

        try:
            response = session.get(
                API_URL,
                params={
                    "coCd": "A420",
                    "siteNo": THEATER_CODE,
                    "scnYmd": date_text,
                    "rtctlScopCd": "08"
                },
                headers={
                    "Accept": "application/json, text/plain, */*",
                    "Accept-Language": "ko-KR,ko;q=0.9",
                    "Referer": BOOKING_PAGE
                },
                timeout=30
            )

            print(
                f"{date_text} 확인 - "
                f"상태코드: {response.status_code}"
            )

            if response.status_code != 200:
                continue

            data = response.json()

            if data.get("statusCode") != 0:
                continue

            schedules = data.get("data") or []

            for schedule in schedules:

                screen_name = schedule.get("scnsNm") or ""
                display_screen_name = schedule.get("expoScnsNm") or ""
                movie_format = schedule.get("movkndDsplNm") or ""

                search_text = " ".join([
                    screen_name,
                    display_screen_name,
                    movie_format
                ]).upper()

                # IMAX가 아닌 상영은 무시
                if "IMAX" not in search_text:
                    continue

                movie_name = (
                    schedule.get("movNm")
                    or schedule.get("prodNm")
                    or "영화명 없음"
                )

                start_time = schedule.get("scnsrtTm") or ""

                schedule_id = (
                    f"{date_text}|"
                    f"{movie_name}|"
                    f"{screen_name}|"
                    f"{start_time}"
                )

                imax_info = {
                    "id": schedule_id,
                    "date": date_text,
                    "movie": movie_name,
                    "screen": display_screen_name or screen_name,
                    "time": start_time
                }

                imax_list.append(imax_info)

                print("🎥 IMAX 발견:", imax_info)

        except Exception as error:
            print(f"{date_text} 확인 중 오류:", error)

    # 중복 제거
    unique_imax = {}

    for item in imax_list:
        unique_imax[item["id"]] = item

    return list(unique_imax.values())


def load_previous_imax():
    if not os.path.exists(STATE_FILE):
        return None

    try:
        with open(
            STATE_FILE,
            "r",
            encoding="utf-8"
        ) as file:
            return json.load(file)

    except Exception:
        return None


def save_imax(imax_list):
    with open(
        STATE_FILE,
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            imax_list,
            file,
            ensure_ascii=False,
            indent=2
        )


def format_time(time_text):
    if len(time_text) == 4:
        return f"{time_text[:2]}:{time_text[2:]}"

    return time_text


def send_discord(new_imax):
    if not WEBHOOK_URL:
        raise Exception("DISCORD_WEBHOOK_URL이 없습니다.")

    message = (
        "🎥 **CGV 광교 IMAX 예매 오픈!**\n\n"
        "새로운 IMAX 상영이 발견되었습니다.\n\n"
    )

    shown = set()

    for item in new_imax:

        key = (
            item["date"],
            item["movie"],
            item["screen"]
        )

        if key in shown:
            continue

        shown.add(key)

        date = datetime.strptime(
            item["date"],
            "%Y%m%d"
        ).strftime("%Y년 %m월 %d일")

        message += (
            f"🎬 **{item['movie']}**\n"
            f"📅 {date}\n"
            f"🎥 {item['screen']}\n\n"
        )

    message += (
        "🔔 CGV 광교에서 예매 가능한 "
        "IMAX 상영이 새로 열렸습니다!"
    )

    response = requests.post(
        WEBHOOK_URL,
        json={"content": message},
        timeout=30,
        impersonate="chrome"
    )

    print("Discord 전송 상태:", response.status_code)

    if response.status_code not in [200, 204]:
        raise Exception(
            f"Discord 전송 실패: {response.status_code}"
        )


def main():

    # 한국 시간 기준 오늘
    today = datetime.now(KST).date()
    today_text = today.strftime("%Y%m%d")

    current_imax = get_imax_schedules()

    print(
        "현재 발견된 IMAX 개수:",
        len(current_imax)
    )

    previous_imax = load_previous_imax()

    # 첫 실행
    if previous_imax is None:

        print("첫 실행입니다.")
        print("현재 IMAX 상태를 기준값으로 저장합니다.")

        save_imax(current_imax)

        print("IMAX 기준값 저장 완료!")

        return

    previous_ids = {
        item["id"]
        for item in previous_imax
    }

    # ⭐ 핵심 수정
    # 오늘보다 이전 날짜는 절대로 알림하지 않음
    new_imax = [
        item
        for item in current_imax
        if (
            item["id"] not in previous_ids
            and item["date"] >= today_text
        )
    ]

    if new_imax:

        print("🔥 새로운 IMAX 상영 발견!")

        for item in new_imax:
            print(item)

        send_discord(new_imax)

    else:

        print("새로운 IMAX 상영이 없습니다.")

    # 현재 상태 저장
    save_imax(current_imax)


if __name__ == "__main__":
    main()
