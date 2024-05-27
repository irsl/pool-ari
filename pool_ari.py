#!/usr/bin/env python3

from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import json
import argparse
import requests
import re
import time
import sys
import os
from datetime import datetime
from collections import namedtuple
from threading import Lock

THROTTLED_PAUSE_SEC = 180
UPSTREAM = "https://www.ariston-net.remotethermo.com"
class Cred:
    usr = None
    pwd = None
class Session:
    in_use = False # by one of the handlers
    throttled = 0 # when the server kicked us out, this is the unix time when this slot may be used again
    token = "" # is it logged in? if so, this is the token
    cred = None
    
    def __str__(self):
        return self.cred.usr

mutex = Lock()
pool = []
pool_index = 0
api_auth = None

def eprint(*args, **kwargs):
    now_str = datetime.now().replace(microsecond=0).isoformat()
    print(f"[{now_str}]", *args, **kwargs, file=sys.stderr)

def _iterate_pool():
    global pool_index
    original_index = pool_index
    while pool_index < len(pool):
        yield pool[pool_index]
        pool_index += 1
    pool_index = 0
    while pool_index < original_index:
        yield pool[pool_index]
        pool_index += 1

def obtain_pool_entry():
    with mutex:
        now = time.time()
        for session in _iterate_pool():
            if session.in_use:
                continue
            if session.throttled and session.throttled > now:
                continue
            session.throttled = 0
            session.in_use = True
            return session

def ensure_logged_in(session, user_agent):
    try:
        if session.token:
            return
        eprint("logging in to upstream", session.cred.usr)
        response = requests.post(
            UPSTREAM+"/api/v2/accounts/login",
            json={"usr": session.cred.usr, "pwd": session.cred.pwd},
            headers={"Content-Type":"application/json", "User-Agent": user_agent}
        )
        rj = response.json()
        session.token = rj["token"]
        eprint("login response received", response.status_code, json.dumps(rj))
    finally:
        session.in_use = False

# same as the previous, but also attempts to login, if needed
def obtain_session(user_agent):
    session = obtain_pool_entry()
    if session:
        eprint("session found", session)
        ensure_logged_in(session, user_agent)
    else:
        eprint("no free slot found")
    return session

class AriHTTPRequestHandler(BaseHTTPRequestHandler):

    def __getattr__(self,name):
        if name.startswith("do_"):
            return self._do
        return super().__getattr__(name)

    def _respond(self, code, raw_response_body, headers={}):
        self.send_response(code)
        for key in headers:
            self.send_header(key, headers[key])
        self.send_header("Content-Length", str(len(raw_response_body)))
        self.end_headers()
        self.wfile.write(raw_response_body)
        self.wfile.flush()
        eprint("response", code, raw_response_body, headers)
        
    def _respond_json(self, code, data, headers={}):
        raw_response_body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
        self._respond(code, raw_response_body, headers)
        
    def _send_upstream(self, session, data):
        url = UPSTREAM+self.path
        h = dict(self.headers)
        for d in ["Host", "ar.authtoken", "ar.authToken", "Content-Length", "Content-Encoding", "Transfer-Encoding"]:
            h.pop(d, None)
        h["Ar.authtoken"] = session.token
        eprint("sending request to upstream", self.command, url, json.dumps(data), h)
        response = requests.request(self.command, headers=h, url=url, json=data)
        raw_response_body = response.content
        h = dict(response.headers)
        for d in ["Content-Length", "Connection", "Date"]:
            h.pop(d, None)
        eprint("upstream response received", response.status_code, raw_response_body, h)
        return (response.status_code, raw_response_body, h)

    def _do(self):
        cl = int(self.headers.get("Content-Length") or 0)
        data = None
        if cl:
            data = json.loads(self.rfile.read(cl))
        eprint("incoming request", self.command, self.path, json.dumps(data))
        expected_token = f"{api_auth.usr}:{api_auth.pwd}"
        if "/accounts/login" in self.path:
            if data["usr"] != api_auth.usr or data["pwd"] != api_auth.pwd:
                return self._respond_json(403, {"error":"invalid usr or pwd"})
            return self._respond_json(200, {"token": expected_token})
        # authorize the request based on the API credentials
        if self.headers["Ar.authtoken"] != expected_token:
            return self._respond_json(403, {"error":"invalid token"})
        # at this point the request is authorized and it is not a login request, so relaying to the upstream is needed
        session = None
        try:
            session = obtain_session(self.headers["User-Agent"])
            if session:
                (code, body, headers) = self._send_upstream(session, data)
                if code >= 400:
                    if code == 429:
                        session.throttled = time.time()+THROTTLED_PAUSE_SEC
                    elif code in [404]:
                        pass
                    else:
                        # some another error, probably better to relogin next time
                        session.token = ""
                return self._respond(code, body, headers)
        except Exception as e:
            eprint("error", e)
            self._respond_json(500, {"error":str(e)})
        finally:
            if session: session.in_use = False        

def do_the_job(args):
    eprint(f"Listening on {args.listen_host} : {args.listen_port}")

    httpd = ThreadingHTTPServer((args.listen_host, args.listen_port), AriHTTPRequestHandler)
    httpd.serve_forever()

def parse_creds_by_prefix(prefix):
    r = Cred()
    r.usr = os.getenv(prefix+"_USR")
    r.pwd = os.getenv(prefix+"_PWD")
    if not r.usr: raise Exception(prefix+"_USR must be set")
    if not r.pwd: raise Exception(prefix+"_PWD must be set")
    return r

# we parse these from the environment variables so they wont show up in the process list
def parse_creds():
    api_auth = parse_creds_by_prefix("AUTH")
    n = 0
    pool = []
    while True:
        prefix = f"POOL_{n}"
        if not os.getenv(prefix+"_USR"):
            break
        c = parse_creds_by_prefix(prefix)
        s = Session()
        s.cred = c
        pool.append(s)
        n+= 1
    if len(pool) == 0:
        raise Exception("No credentials configured for the pool!")
    eprint(f"Configured {len(pool)} credentials for the pool")
    return api_auth, pool
        

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--listen-host", default="0.0.0.0", help="host to listen on")
    parser.add_argument("--listen-port", type=int, default=9999, help="port to listen on")
    args = parser.parse_args()
    (api_auth, pool) = parse_creds()
    do_the_job(args)
