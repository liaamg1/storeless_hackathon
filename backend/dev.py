"""Run the API and its automatic worker with reload restricted to application code."""
import os
from pathlib import Path

import uvicorn

BACKEND_DIR = Path(__file__).resolve().parent


if __name__ == '__main__':
    os.chdir(BACKEND_DIR)
    uvicorn.run('main:app', host='127.0.0.1', port=8000, reload=True,
                reload_dirs=[str(BACKEND_DIR / 'app')])
