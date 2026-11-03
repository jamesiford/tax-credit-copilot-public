"""Hosted-agent entry point at the zip root: `python main.py`. [CH-08]

The source-code deployment runs `entryPoint: [python, main.py]` from the root of the uploaded zip.
All of the code is in `app/`; this file only starts it, so the same entry works for the container path.
"""
from app.main import main

if __name__ == "__main__":
    main()
