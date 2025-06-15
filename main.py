import json
import os
import sys
import asyncio
from io import BytesIO

import aiohttp
from fastapi import Request, FastAPI, HTTPException
from zoneinfo import ZoneInfo

from linebot.models import (
    MessageEvent,
    TextSendMessage,
    FlexSendMessage,
    FlexContainer,
    FlexComponent,
)
from linebot.exceptions import InvalidSignatureError
from linebot.aiohttp_async_http_client import AiohttpAsyncHttpClient
from linebot import AsyncLineBotApi, WebhookParser
from multi_tool_agent.agent import (
    get_current_time,
    parse_event,
)
from google.adk.agents import Agent
from line_flex import build_event_flex

# Import necessary session components
from google.adk.sessions import InMemorySessionService, Session
from google.adk.runners import Runner
from google.genai import types

# use dotenv to load environment variables from .env file
from dotenv import load_dotenv

load_dotenv()

# OpenAI Agent configuration
USE_VERTEX = os.getenv("GOOGLE_GENAI_USE_VERTEXAI") or "FALSE"
GOOGLE_API_KEY = os.getenv("GEMINI_API_KEY") or ""

# LINE Bot configuration
channel_secret = os.getenv("ChannelSecret", None)
channel_access_token = os.getenv("ChannelAccessToken", None)

# Validate environment variables
if channel_secret is None:
    print("Specify ChannelSecret as environment variable.")
    sys.exit(1)
if channel_access_token is None:
    print("Specify ChannelAccessToken as environment variable.")
    sys.exit(1)
if USE_VERTEX == "True":  # Check if USE_VERTEX is true as a string
    GOOGLE_CLOUD_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT")
    GOOGLE_CLOUD_LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION")
    if not GOOGLE_CLOUD_PROJECT:
        raise ValueError(
            "Please set GOOGLE_CLOUD_PROJECT via env var or code when USE_VERTEX is true."
        )
    if not GOOGLE_CLOUD_LOCATION:
        raise ValueError(
            "Please set GOOGLE_CLOUD_LOCATION via env var or code when USE_VERTEX is true."
        )
elif not GOOGLE_API_KEY:
    raise ValueError("Please set GOOGLE_API_KEY via env var or code.")

# Initialize the FastAPI app for LINEBot
app = FastAPI()
session = aiohttp.ClientSession()
async_http_client = AiohttpAsyncHttpClient(session)
line_bot_api = AsyncLineBotApi(channel_access_token, async_http_client)
parser = WebhookParser(channel_secret)

# Initialize ADK client
root_agent = Agent(
    model="gemini-2.0-flash",
    name="root_agent",
    description="判斷訊息是否為事件，並以 JSON 包裝結果",
    instruction=(
        """
            你是一個 LINE 群組的活動助理，從自然語言訊息中判斷是否包含事件資訊。

            你必須使用 `get_current_time` function 來解析「明天」、「下星期一」等模糊時間。

            你應從最近兩則訊息中推理是否能夠組合成一個完整的事件。

            請根據以下情況輸出 JSON：

            1. 如果訊息與事件無關，請回傳：
            {"type": "NoResponse"}

            2. 如果訊息可能是事件，但資訊不完整（缺日期或時間），請回傳：
            {"type": "NeedMoreDetails", "data": {"message": ... }}

            3. 如果訊息是完整的事件，請回傳：
            {"type": "Event", "data": {"title": ..., "date": ..., "time": ..., "note": ...}}

            注意：
            - title 為活動主題，例如「開會」、「打球」。
            - note 可加入提醒，例如「請帶鉛筆盒」，若無則為空字串。
            - 請不要重複問同樣問題。
            - 若你已知前面訊息中已有資訊，就不要再次詢問。
            """
    ),
    tools=[parse_event, get_current_time],
)
print(f"Agent '{root_agent.name}' created.")

# --- Session Management ---
# Key Concept: SessionService stores conversation history & state.
# InMemorySessionService is simple, non-persistent storage for this tutorial.
session_service = InMemorySessionService()

# Define constants for identifying the interaction context
APP_NAME = "EventMind"
# Instead of fixed user_id and session_id, we'll now manage them dynamically

# Dictionary to track active sessions
active_sessions = {}

# Create a function to get or create a session for a user


async def get_or_create_session(user_id):  # Make function async
    if user_id not in active_sessions:
        # Create a new session for this user
        session_id = f"session_{user_id}"
        # Add await for the async session creation
        await session_service.create_session(
            app_name=APP_NAME, user_id=user_id, session_id=session_id
        )
        active_sessions[user_id] = session_id
        print(
            f"New session created: App='{APP_NAME}', User='{user_id}', Session='{session_id}'"
        )
    else:
        # Use existing session
        session_id = active_sessions[user_id]
        print(
            f"Using existing session: App='{APP_NAME}', User='{user_id}', Session='{session_id}'"
        )

    return session_id


# Key Concept: Runner orchestrates the agent execution loop.
runner = Runner(
    agent=root_agent,  # The agent we want to run
    app_name=APP_NAME,  # Associates runs with our app
    session_service=session_service,  # Uses our session manager
)
print(f"Runner created for agent '{runner.agent.name}'.")


@app.post("/callback")
async def handle_callback(request: Request):
    signature = request.headers["X-Line-Signature"]

    # get request body as text
    body = await request.body()
    body = body.decode()

    try:
        events = parser.parse(body, signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    for event in events:
        if not isinstance(event, MessageEvent):
            continue

        if event.message.type == "text":
            # Process text message
            msg = event.message.text
            user_id = event.source.user_id
            print(f"Received message: {msg} from user: {user_id}")

            # Use the user's prompt directly with the agent
            response = await call_agent_async(
                f"現在時間是 {get_current_time()}，請以此為基準處理「明天」、「後天」、「下週一」、「今天下午」等模糊時間\n user message:{msg}",
                user_id=user_id,
            )
            response = (
                response.replace("```json", "").replace("`", "").strip()
            )  # Clean up the response
            reply_msg = None
            try:
                data = json.loads(response)
                if data.get("type") == "NoResponse":
                    return "OK"  # No response needed
                elif data.get("type") == "NeedMoreDetails":
                    reply_msg = TextSendMessage(text=data["data"]["message"])
                else:
                    # Assume it's an event response
                    event_data = data["data"]
                    event_flex = build_event_flex(
                        title=event_data.get("title", "無標題"),
                        date=event_data.get("date", "未知日期"),
                        time=event_data.get("time", "未知時間"),
                        note=event_data.get("note", ""),
                    )
                    reply_msg = FlexSendMessage(
                        alt_text="事件確認", contents=event_flex
                    )
            except json.JSONDecodeError:
                reply_msg = TextSendMessage(text="發生錯誤")
            await line_bot_api.reply_message(event.reply_token, reply_msg)
        elif event.message.type == "image":
            return "OK"
        else:
            continue

    return "OK"


async def call_agent_async(query: str, user_id: str) -> str:
    """Sends a query to the agent and prints the final response."""
    print(f"\n>>> User Query: {query}")

    # Get or create a session for this user
    session_id = await get_or_create_session(user_id)  # Add await

    # Prepare the user's message in ADK format
    content = types.Content(role="user", parts=[types.Part(text=query)])

    final_response_text = "Agent did not produce a final response."  # Default

    try:
        # Key Concept: run_async executes the agent logic and yields Events.
        # We iterate through events to find the final answer.
        async for event in runner.run_async(
            user_id=user_id, session_id=session_id, new_message=content
        ):
            # You can uncomment the line below to see *all* events during execution
            # print(f"  [Event] Author: {event.author}, Type: {type(event).__name__}, Final: {event.is_final_response()}, Content: {event.content}")

            # Key Concept: is_final_response() marks the concluding message for the turn.
            if event.is_final_response():
                if event.content and event.content.parts:
                    # Assuming text response in the first part
                    final_response_text = event.content.parts[0].text
                elif (
                    event.actions and event.actions.escalate
                ):  # Handle potential errors/escalations
                    final_response_text = f"Agent escalated: {event.error_message or 'No specific message.'}"
                # Add more checks here if needed (e.g., specific error codes)
                break  # Stop processing events once the final response is found
    except ValueError as e:
        # Handle errors, especially session not found
        print(f"Error processing request: {str(e)}")
        # Recreate session if it was lost
        if "Session not found" in str(e):
            active_sessions.pop(user_id, None)  # Remove the invalid session
            session_id = await get_or_create_session(
                user_id
            )  # Create a new one # Add await
            # Try again with the new session
            try:
                async for event in runner.run_async(
                    user_id=user_id, session_id=session_id, new_message=content
                ):
                    # Same event handling code as above
                    if event.is_final_response():
                        if event.content and event.content.parts:
                            final_response_text = event.content.parts[0].text
                        elif event.actions and event.actions.escalate:
                            final_response_text = f"Agent escalated: {event.error_message or 'No specific message.'}"
                        break
            except Exception as e2:
                final_response_text = f"Sorry, I encountered an error: {str(e2)}"
        else:
            final_response_text = f"Sorry, I encountered an error: {str(e)}"

    print(f"<<< Agent Response: {final_response_text}")
    return final_response_text