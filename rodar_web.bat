@echo off
pip install -r requirements.txt
python -m streamlit run streamlit_app.py --server.port 8501 --server.headless true
