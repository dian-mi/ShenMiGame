# Mystery Game (Streamlit)

This repo is prepared to run on **Streamlit Cloud**.

## Files
- `streamlit_app.py` : Streamlit entrypoint
- `engine_core.py`   : game engine (no tkinter). Exposes both `Engine` and `GameEngine`.
- `requirements.txt` : pinned dependencies

## Local Run
```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Streamlit Cloud
- App file path: `streamlit_app.py`
- Python: default
