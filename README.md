ClubHouse API

live demo: https://clubhouse-jph6.onrender.com/docs

A scalable, modular backend built with FastAPI, Async SQLAlchemy, PostgreSQL, and WebSockets. ClubHouse API powers a social‑collaboration platform with features such as:

Authentication & Profiles

Blogging & Comments

Reactions & Shares

Personal Targets & Group Tasks

Communities (Groups)

Participants & Assignments

Opinions & Voting

Direct Messaging

Real‑Time WebSocket Chat

This README documents the entire API in a clean, production‑ready format.

Features Overview 

✅ Authentication JWT‑based login, registration, refresh, and logout.

✅ User Profiles View, edit, search, and delete profiles.

✅ Blogging System Create blogs with images, view, search, discover trending posts, edit, and delete.

✅ Comments Comment on blogs, view, search, edit, delete, and discover trending comments.

✅ Reactions React to blogs or comments.

✅ Shares Share blogs with optional captions and reactions.

✅ Personal Targets Create tasks, track savings, contributions, feasibility checks, completion, and deletion.

✅ Group Tasks Collaborative tasks with savings, contributions, completion tracking, and feasibility checks.

✅ Communities (Groups) Create groups, edit, add admins, add/remove members, list groups and members.

✅ Participants Assign participants to group tasks, track assignment completion and payments.

✅ Opinions & Voting Suggest ideas for group tasks, view opinions, vote, and delete.

✅ Direct Messaging Send text or images, view conversations, delete messages or entire chats.

✅ Real‑Time WebSocket Chat Live messaging with delivery tracking, offline message replay, and missed‑chat email notifications.

Tech Stack FastAPI (async)

SQLAlchemy Async ORM

PostgreSQL

Alembic (migrations)

JWT Authentication

WebSockets

Celery + Redis

Pydantic Models

Setup & Installation

Clone the repository
git clone https://github.com/CodeEmmanuel-beep/clubHouse.git cd clubhouse-api

Create a virtual environment
python -m venv venv source venv/bin/activate # macOS/Linux venv\Scripts\activate # Windows

Install dependencies
pip install -r requirements.txt

Configure environment variables Create a .env file:
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/clubhouse SECRET_KEY=your_secret_key ALGORITHM=HS256 ACCESS_TOKEN_EXPIRE_MINUTES=60

Run migrations
alembic upgrade head

Start the server
uvicorn app.main:app --reload

API Documentation Below is a structured summary of all modules. Each module has its own detailed section:

🔐 Authentication API Prefix: /auth

Register

Login

Refresh token

Logout

👤 Profile API Prefix: /info

View profile

Search users

Edit profile

Delete profile

📝 Blog API Prefix: /blogs

Create blog

View blogs

Search blogs

Trending blogs

View one

Edit

Delete

💬 Comments API Prefix: /comment

Add comment

View comments

View one

Trending

Edit

Delete

❤️ Reactions API Prefix: /react

React to blog or comment

🔗 Share API Prefix: /sharing

Share blog

View shares

View one

Delete

🎯 Personal Target API Prefix: /plot

Create task

Savings

Contributions

Feasibility checks

List tasks

Completed / undone

Delete

👥 Group Tasks API Prefix: /g_tasks

Create group task

Update

Savings

Contributions

Completed tasks

Delete

🧑‍🤝‍🧑 Communities (Groups) API Prefix: /group

Create group

Edit

Add admin

Add member

View admins

View members

View groups

Remove member

👤 Participants API Prefix: /member

Add participant

View participants

Mark assignment complete

Mark payment complete

Delete participant

🗳️ Opinion & Voting API Prefix: /suggest

Create opinion

View opinions

Vote

Delete opinion

💬 Direct Messaging API Prefix: /message

Send message

View messages

View conversation

Delete message

Clear conversation

WebSocket Chat API Prefix: /Chatbox

Real‑time chat

Text support

Delivery tracking

Offline message replay

Missed‑chat email notifications

👨‍💻 Author Emmanuel Eke

Email: emmanuelchiedueke01@gmail.com
