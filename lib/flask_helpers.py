import logging
import sys
from threading import Thread
import webbrowser
from time import sleep
from io import BytesIO
try:
    from flask import make_response, send_file
except ImportError:
    sys.exit("Cannot import from flask: Do `pip3 install --user flask` to install")



def _delayed_open_web_browser(url, delay, new=0, autoraise=True, specific_browser=None):
    def _sleep_and_open_web_browser(url, delay, new, autoraise, specific_browser):
        sleep(delay)
        browser = webbrowser

        # E.g. On OSX the following would use the Chrome browser app from that location
        # specific_browser = 'open -a /Applications/Google\ Chrome.app %s'
        if specific_browser:
            browser = webbrowser.get(specific_browser)

        browser.open(url, new=new, autoraise=autoraise)

    thread = Thread(target=_sleep_and_open_web_browser,
                    kwargs=dict(url=url, new=new, autoraise=autoraise, delay=delay, specific_browser=specific_browser))
    thread.daemon = True # Force to quit on main quitting
    thread.start()


def run_flask(flask_app, host_ip="0.0.0.0", host_port=5000, enable_flask_logging=False,
              open_page=True, open_page_delay=1.0):
    if not enable_flask_logging:
        # disable logging in Flask (it's enabled by default)
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)

    if open_page:
        # we add a delay (dispatched in another thread) to open the page so that the flask webserver is open
        # before the webpage requests any data
        _delayed_open_web_browser("http://" + host_ip + ":" + str(host_port), delay=open_page_delay)

    flask_app.run(host=host_ip, port=host_port, use_evalex=False)


def make_uncached_response(in_file):
    response = make_response(in_file)
    response.headers['Pragma-Directive'] = 'no-cache'
    response.headers['Cache-Directive'] = 'no-cache'
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


def serve_pil_image(pil_img, serve_as_jpeg=False, jpeg_quality=70):
    img_io = BytesIO()

    if serve_as_jpeg:
        pil_img.save(img_io, 'JPEG', quality=jpeg_quality)
        img_io.seek(0)
        return make_uncached_response(send_file(img_io, mimetype='image/jpeg'))
    else:
        pil_img.save(img_io, 'PNG')
        img_io.seek(0)
        return make_uncached_response(send_file(img_io, mimetype='image/png'))
