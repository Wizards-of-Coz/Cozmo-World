#!/usr/bin/env python3

# Copyright (c) 2016 Anki, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License in the file LICENSE.txt or at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

'''Control Cozmo using a webpage on your computer.

This example lets you control Cozmo by Remote Control, using a webpage served by Flask.
'''

import json
import sys

sys.path.append('lib/')
import flask_helpers
import cozmo
import math
import random


try:
    from flask import Flask, request
except ImportError:
    sys.exit("Cannot import from flask: Do `pip3 install --user flask` to install")

try:
    from PIL import Image, ImageDraw
except ImportError:
    sys.exit("Cannot import from PIL: Do `pip3 install --user Pillow` to install")


flask_app = Flask(__name__)
remote_control_cozmo = None

class RemoteControlCozmo:

    reactionDict = {"happy" : {"emo":['anim_memorymatch_successhand_cozmo_02','anim_memorymatch_successhand_player_02','anim_rtpkeepaway_playeryes_03','anim_rtpkeepaway_playeryes_02','anim_sparking_success_01','anim_reacttoblock_ask_01','anim_reacttoblock_happydetermined_02']},
                    "very_happy":{'emo':['anim_memorymatch_successhand_cozmo_03','anim_memorymatch_successhand_cozmo_04']},
                    "sad":{'emo':['anim_driving_upset_start_01','anim_memorymatch_failgame_cozmo_03','anim_keepaway_losegame_02']},
                    "angry":{'emo':['anim_bored_01','anim_bored_02','anim_keepaway_losegame_03','anim_keepaway_losehand_03','anim_speedtap_lookatplayer','anim_reacttoblock_frustrated_01','anim_reacttoblock_frustrated_int2_01']},
                    "idle":{'emo':['anim_sparking_idle_03']},
                    "bored":{'emo':['anim_bored_01','anim_bored_02','anim_bored_event_01','anim_bored_event_02','anim_bored_event_04']}}
    def __init__(self, coz):
        self.cozmo = coz

        self.action_queue = []

        self.lift_up = 0
        self.lift_down = 0
        self.head_up = 0
        self.head_down = 0

        self.text_to_say = "Hi I'm Cozmo"

        self.anims_for_keys = ["idle","bored",  # 1
                                  "angry",  # 2
                                  "sad",  # 3
                                  "happy",  # 4
                                  "very_happy",  # 5
                                 ]

    def joystick_start(self):
        self.cozmo.drive_wheels(0,0,0,0)

    def joystick_end(self):
        self.cozmo.drive_wheels(0,0,0,0)

    def joystick_move(self,angle,force):
        forward_speed = 50 + force*25;
        turn_speed = 50 + force*25;
        angle = round(angle/5)*5;

        if(angle > 0 and angle < 180):
            drive_dir = 1;
            turn_dir = (90 - angle)/90;
        else:
            drive_dir = -1;
            turn_dir = (270-angle)/90;

        l_wheel_speed = (drive_dir * forward_speed) + (turn_speed * turn_dir)
        r_wheel_speed = (drive_dir * forward_speed) - (turn_speed * turn_dir)

        self.cozmo.drive_wheels(l_wheel_speed, r_wheel_speed, l_wheel_speed*4, r_wheel_speed*4)

    def queue_action(self, new_action):
        if len(self.action_queue) > 10:
            self.action_queue.pop(0)
        self.action_queue.append(new_action)


    def try_say_text(self, text_to_say):
        try:
            self.cozmo.say_text(text_to_say)
            return True
        except cozmo.exceptions.RobotBusy:
            return False


    def try_play_anim(self, anim_name):
        try:
            self.cozmo.play_anim(name=anim_name)
            return True
        except cozmo.exceptions.RobotBusy:
            return False


    def handle_key(self, key_code, is_key_down):
        '''Called on any key press or release
           Holding a key down may result in repeated handle_key calls with is_key_down==True
        '''
        # Handle any keys being released (e.g. the end of a key-click)
        if not is_key_down:
            if (key_code >= ord('0')) and (key_code <= ord('5')):
                anim_name = self.key_code_to_anim_name(key_code)
                self.play_animation(anim_name)
            elif key_code == ord(' '):
                self.say_text(self.text_to_say)

    def key_code_to_anim_name(self, key_code):
        key_num = key_code - ord('0')
        anim_category = self.anims_for_keys[key_num]
        category_arr = self.reactionDict[anim_category]['emo']
        anim_name = random.choice (category_arr)
        return anim_name

    def say_text(self, text_to_say):
        self.queue_action((self.try_say_text, text_to_say))
        self.update()


    def play_animation(self, anim_name):
        self.queue_action((self.try_play_anim, anim_name))
        self.update()


    def update(self):
        '''Try and execute the next queued action'''
        if len(self.action_queue) > 0:
            queued_action, action_args = self.action_queue[0]
            if queued_action(action_args):
                self.action_queue.pop(0)

    def update_lift(self, up_or_down):
        lift_speed = 2;
        lift_vel = up_or_down * lift_speed
        self.cozmo.move_lift(lift_vel)


    def update_head(self, up_or_down):
        head_speed = 1;
        head_vel = up_or_down * head_speed
        self.cozmo.move_head(head_vel)

@flask_app.route("/")
def handle_index_page():
    return '''
    <html>
        <head>
            <title>remote_control_cozmo.py display</title>
            <link type="text/css" rel="stylesheet" href="static/styles.css"/>
            <script src="static/dist/nipplejs.js" charset="utf-8"></script>
        </head>
        <body>
            <h1 style="text-align:center">Welcome to Cozmo World</h1>
            <div id="left"></div>
            <div id="right"></div>
            <table>
                <tr height=10></tr>
                <tr height=50>
                <td width=10></td>
                <td width=300></td>
                <td width=340></td>
                <td valign=top width=300>
                    <button class = "button" type="button" onClick="controlHead()">Control Head</button>
                    &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
                    <button class = "button" type="button" onClick="controlLift()">Control Lift</button>
                </td>
                </tr>
                <tr>
                    <td width=10></td>
                    <td valign=top>
                        <h2>Control Movement</h2>
                    </td>
                    <td width=340></td>
                    <td valign=top>
                        <h2 id="headLiftText">Controlling Head</h2>
                    </td>
                </tr>
            </table>

            <script type="text/javascript">
                var gisControllingHead = true

                function controlLift() {
                    gisControllingHead = false;
                    document.getElementById('headLiftText').innerHTML = "Controlling Lift"
                }

                function controlHead() {
                    gisControllingHead = true;
                    document.getElementById('headLiftText').innerHTML = "Controlling Head"
                }

                var joystickL = nipplejs.create({
                    zone: document.getElementById('left'),
                    mode: 'static',
                    position: { left: '15%', top: '25%' },
                    color: 'orange',
                    size: 200
                });

                var joystickR = nipplejs.create({
                    zone: document.getElementById('right'),
                    mode: 'static',
                    position: { left: '60%', top: '25%' },
                    color: '#4CAF50',
                    size: 200
                });

                function doOnOrientationChange() {
                    
                    switch(window.orientation) 
                    {  
                      case -90:
                      case 90:
                      console.log("landscape");
                        var right = document.getElementById('nipple_1_1');
                        right.style.left = '80%';
                        right.style.top = '63%';
                        var left = document.getElementById('nipple_0_0');
                        left.style.left = '17%';
                        left.style.top = '63%';
                        break; 
                      default:
                      console.log("portrait");
                        var right = document.getElementById('nipple_1_1');
                        right.style.left = '80%';
                        right.style.top = '25%';
                        var left = document.getElementById('nipple_0_0');
                        left.style.left = '15%';
                        left.style.top = '25%';
                        break; 
                    }
                }

                  window.addEventListener('orientationchange', doOnOrientationChange);

                  // Initial execution if needed
                  doOnOrientationChange();

                function bindNipple () {
                    joystickR.on('end', function (evt, data) {
                        headLiftEnd(data);
                    }).on('move', function (evt, data) {
                        headLiftMove(data);
                    });

                    joystickL.on('start', function (evt, data) {
                        startJoystick(data);
                    }).on('end', function (evt, data) {
                        endJoystick(data);
                    }).on('move', function (evt, data) {
                        debug(data);
                    });
                }
                bindNipple();

                function headLiftEnd(obj) {
                    console.log("End");
                    msg = "End";
                    if(gisControllingHead) {
                        postHttpRequest("headEnd", {msg})
                    } else{
                        postHttpRequest("liftEnd", {msg})    
                    }
                }
                function headLiftMove (obj) {
                    angle = obj.angle.degree;
                    force = obj.force
                    console.log(angle);
                    console.log(force);
                    if(gisControllingHead) {
                        postHttpRequest("headMove", {angle,force})
                    } else{
                        postHttpRequest("liftMove", {angle,force})
                    }
                }

                function startJoystick(obj) {
                    console.log("Start");
                    msg = "Start";
                    postHttpRequest("joystickStart", {msg})
                }
                function endJoystick(obj) {
                    console.log("End");
                    msg = "End";
                    postHttpRequest("joystickEnd", {msg})
                }
                function debug (obj) {
                    angle = obj.angle.degree;
                    force = obj.force
                    console.log(angle);
                    console.log(force);
                    postHttpRequest("joystickMove", {angle,force})
                }

                function postHttpRequest(url, dataSet)
                {
                    var xhr = new XMLHttpRequest();
                    xhr.open("POST", url, true);
                    xhr.send( JSON.stringify( dataSet ) );
                }

                function updateCozmo()
                {
                    postHttpRequest("updateCozmo", {} )
                }
                setInterval(updateCozmo , 60);

                function handleKeyActivity (e, actionType)
                {
                    var keyCode  = (e.keyCode ? e.keyCode : e.which);
                    postHttpRequest(actionType, {keyCode})
                }

                document.addEventListener("keydown", function(e) { handleKeyActivity(e, "keydown") } );
                document.addEventListener("keyup", function(e) { handleKeyActivity(e, "keyup") } );

                function stopEventPropagation(event)
                {
                    if (event.stopPropagation)
                    {
                        event.stopPropagation();
                    }
                    else
                    {
                        event.cancelBubble = true
                    }
                }
            </script>

        </body>
    </html>
    '''


@flask_app.route('/updateCozmo', methods=['POST'])
def handle_updateCozmo():
    '''Called very frequently from Javascript to provide an update loop'''
    if remote_control_cozmo:
        remote_control_cozmo.update()
    return ""

@flask_app.route('/sayText', methods=['POST'])
def handle_sayText():
    '''Called from Javascript whenever the saytext text field is modified'''
    message = json.loads(request.data.decode("utf-8"))
    if remote_control_cozmo:
        remote_control_cozmo.text_to_say = message['textEntered']
        remote_control_cozmo.try_say_text(remote_control_cozmo.text_to_say);
    return ""

@flask_app.route('/joystickMove', methods=['POST'])
def handle_joystickPosition():
    '''Called from Javascript whenever the joystick position is modified'''
    message = json.loads(request.data.decode("utf-8"))
    if remote_control_cozmo:
        remote_control_cozmo.joystick_move(message['angle'],message['force']);
    return ""

@flask_app.route('/joystickStart', methods=['POST'])
def handle_joystickStart():
    '''Called from Javascript whenever the joystick position is modified'''
    message = json.loads(request.data.decode("utf-8"))
    if remote_control_cozmo:
        remote_control_cozmo.joystick_start();
    return ""

@flask_app.route('/joystickEnd', methods=['POST'])
def handle_joystickEnd():
    '''Called from Javascript whenever the joystick position is modified'''
    message = json.loads(request.data.decode("utf-8"))
    if remote_control_cozmo:
        remote_control_cozmo.joystick_end();
    return ""

@flask_app.route('/liftMove', methods=['POST'])
def handle_liftMove():
    '''Called from Javascript whenever the joystick position is modified'''
    message = json.loads(request.data.decode("utf-8"))
    if remote_control_cozmo:
        if(message['angle'] < 180):
            remote_control_cozmo.update_lift(1);
        else:
            remote_control_cozmo.update_lift(-1);
    return ""

@flask_app.route('/liftEnd', methods=['POST'])
def handle_liftEnd():
    '''Called from Javascript whenever the joystick position is modified'''
    message = json.loads(request.data.decode("utf-8"))
    if remote_control_cozmo:
        remote_control_cozmo.update_lift(0);
    return ""

@flask_app.route('/headMove', methods=['POST'])
def handle_headMove():
    '''Called from Javascript whenever the joystick position is modified'''
    message = json.loads(request.data.decode("utf-8"))
    if remote_control_cozmo:
        if(message['angle'] < 180):
            remote_control_cozmo.update_head(1);
        else:
            remote_control_cozmo.update_head(-1);
    return ""

@flask_app.route('/headEnd', methods=['POST'])
def handle_headEnd():
    '''Called from Javascript whenever the joystick position is modified'''
    message = json.loads(request.data.decode("utf-8"))
    if remote_control_cozmo:
        remote_control_cozmo.update_head(0);
    return ""

@flask_app.route('/keydown', methods=['POST'])
def handle_keydown():
    '''Called from Javascript whenever a key is down (note: can generate repeat calls if held down)'''
    return handle_key_event(request, is_key_down=True)

@flask_app.route('/keyup', methods=['POST'])
def handle_keyup():
    '''Called from Javascript whenever a key is down (note: can generate repeat calls if held down)'''
    return handle_key_event(request, is_key_down=False)

def handle_key_event(key_request, is_key_down):
    message = json.loads(key_request.data.decode("utf-8"))
    if remote_control_cozmo:
        remote_control_cozmo.handle_key(key_code=(message['keyCode']), is_key_down=is_key_down)
    return ""

def run(sdk_conn):
    robot = sdk_conn.wait_for_robot()

    global remote_control_cozmo
    remote_control_cozmo = RemoteControlCozmo(robot)

    flask_helpers.run_flask(flask_app)

if __name__ == '__main__':
    cozmo.setup_basic_logging()
    cozmo.robot.Robot.drive_off_charger_on_connect = False  # RC can drive off charger if required
    try:
        cozmo.connect(run)
    except cozmo.ConnectionError as e:
        sys.exit("A connection error occurred: %s" % e)
