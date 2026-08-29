cp .env.example .env
# Edit .env and set the real Obsidian token before starting the server.

make install   # install dependencies
make dev       # run uvicorn + ngrok together
make serve     # run only uvicorn (PORT=8000 by default)
make tunnel    # run only ngrok
