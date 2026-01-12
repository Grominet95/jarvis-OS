import os
import threading
from os.path import join
from dotenv import load_dotenv

"""
os.getcwd() is the same as when we run it from npm run start:tcp-server en
and when we run it from the binary
"""
dotenv_path = join(os.getcwd(), '.env')
load_dotenv(dotenv_path)

import lib.nlp as nlp
from lib.tcp_server import TCPServer

nlp.load_spacy_model()

tcp_server_host = os.environ.get('LEON_PY_TCP_SERVER_HOST', '0.0.0.0')
tcp_server_port = os.environ.get('LEON_PY_TCP_SERVER_PORT', 1342)

tcp_server = TCPServer(tcp_server_host, tcp_server_port)

# Use thread as ASR starts recording audio and it blocks the main thread
asr_thread = threading.Thread(target=tcp_server.init_asr)
asr_thread.start()

tcp_server.init_tts()

tcp_server_thread = threading.Thread(target=tcp_server.init)
tcp_server_thread.start()
