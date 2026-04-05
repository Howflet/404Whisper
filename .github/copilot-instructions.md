# 404Whisper — AI Agent Instructions

## What This Project Is
404Whisper is a messaging app like WhatsApp or Telegram, but it works without needing a phone number or email. It uses a special system called the Session protocol to send messages securely through the internet. The app runs in your web browser and stores everything on your own computer.

## How It's Built
The code is organized into 8 parts, like layers in a cake. Each layer has its own job:

1. **Identity & Auth** (`identity/`): Creates your secret keys and passwords, saves them safely
2. **Cryptography** (`crypto/`): Handles all the secret code stuff to keep messages private
3. **Network** (`network/`): Figures out how to send messages through the internet safely
4. **Messaging** (`messaging/`): Turns messages into computer code and back again
5. **Groups** (`groups/`): Manages group chats and who can join
6. **Attachments** (`attachments/`): Handles sending files like photos
7. **Storage** (`storage/`): Saves all your data in a secret database on your computer
8. **Web Interface** (`api/` + `frontend/`): The website part you see in the browser

## Important Rules
- **Names**: In the website code, use wordsLikeThis. In Python and database, use words_like_this. For special lists, use WORDS_LIKE_THIS
- **Speed**: All website code must run without stopping other things
- **User IDs**: Every user has a special 66-character code starting with "05" — check it's right before sending
- **Errors**: Use the same error messages from our rules book
- **Themes**: You can change how the app looks, but some changes affect everyone in a group
- **No extras**: Only use Python, no other languages or outside services

## How to Work on It
- **Start the server**: Go to the 404whisper folder and run `python main.py` (it runs on port 8000)
- **Start the website**: Go to the frontend folder and run `npm run dev` (port 5173, connects to server)
- **Test it**: Run `pytest` to check if code works
- **Database**: Your data is locked with a password; use "test123" when testing
- **Live updates**: Messages appear instantly using special connections

## Important Tips
- **Keep things separate**: Don't mix secret code with saving data — each part stays in its folder
- **Test everything**: Secret code must work alone and match examples from Session
- **Safe sending**: Messages get wrapped in 3 layers of protection
- **Message format**: Use special code format from Session
- **Local only**: Everything stays on your computer, nothing goes to the cloud

## How Parts Connect
- **Website to server**: The browser talks to the server only on your computer
- **Protocol guide**: Look at session.js for how things should work (but don't copy it)
- **No outside help**: The app works all by itself
- **File safety**: Files get locked before sending

Read `CONTEXT.md`, `DATA_CONTRACT.md`, `PROGRESS.md` for more details.