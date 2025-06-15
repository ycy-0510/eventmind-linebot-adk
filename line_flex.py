from urllib.parse import quote_plus

def build_event_flex(title: str, date: str, time: str, note: str = ""):
    # 將 date 和 time 組合成 start 與 end 時間（這裡假設活動持續 1 小時）
    start_datetime = f"{date}T{time}"
    
    # 自動產生一小時後的結束時間
    from datetime import datetime, timedelta
    
    # 1. Parse with correct format
    dt_start = datetime.strptime(start_datetime, "%Y-%m-%dT%H:%M")
    dt_end = dt_start + timedelta(hours=1)

    # 2. Format for Google Calendar link
    start_gcal = dt_start.strftime("%Y%m%dT%H%M")
    end_gcal = dt_end.strftime("%Y%m%dT%H%M")

    # 3. URL encode parameters
    title_enc = quote_plus(title)
    note_enc = quote_plus(note or "無")
    calendar_url = (
        f"https://calendar.google.com/calendar/render?action=TEMPLATE"
        f"&text={title_enc}&details={note_enc}&location=Taipei"
        f"&dates={start_gcal}/{end_gcal}&sf=true&openExternalBrowser=1"
    )

    return {
        "type": "bubble",
        "header": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {"type": "text", "text": "事件確認", "weight": "bold", "size": "lg"}
            ],
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "md",
            "contents": [
                {"type": "text", "text": f"標題：{title}"},
                {"type": "text", "text": f"日期：{date}"},
                {"type": "text", "text": f"時間：{time}"},
                {"type": "text", "text": f"備註：{note or '無'}"},
            ],
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "spacing": "sm",
            "contents": [
                {
                    "type": "button",
                    "style": "primary",
                    "action": {
                        "type": "uri",
                        "label": "新增到行事曆",
                        "uri": calendar_url,
                    },
                }
            ],
        },
    }