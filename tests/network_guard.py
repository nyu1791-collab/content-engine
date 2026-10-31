"""モック外のHTTP/ソケット接続を、アプリの例外処理でも握りつぶせない形で止める。"""
import socket

import requests


class LiveNetworkBlocked(BaseException):
    pass


def _deny(*args, **kwargs):
    raise LiveNetworkBlocked("テストからの実ネットワーク接続は禁止です。通信処理をモックしてください")


requests.sessions.Session.request = _deny
socket.socket.connect = _deny
socket.socket.connect_ex = _deny
socket.create_connection = _deny
socket.getaddrinfo = _deny
