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
sys.path.append('../')
from Common.colors import Colors

sys.path.append('lib/')
import flask_helpers
import _thread
import cozmo
import math
import random
import asyncio
import numpy as np
from cozmo.objects import CustomObjectMarkers, CustomObjectTypes

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

CColors = ["Green", "Red", "Blue", "Yellow", "Magenta"]
Shop = "Shop"
Icecream = "Icecream"

class RemoteControlCozmo:

    reactionDict = {"happy":{'emo':['anim_memorymatch_solo_successgame_player_01','anim_memorymatch_successhand_cozmo_04','anim_memorymatch_successhand_cozmo_02','anim_reacttoblock_success_01']},
                    "sad":{'emo':['anim_memorymatch_failgame_cozmo_03','anim_keepaway_losegame_02','anim_reacttoblock_frustrated_01','anim_reacttoblock_frustrated_int2_01']},
                    "icecream": {'emo': ['anim_greeting_happy_01','anim_greeting_happy_03','anim_fistbump_success_01']},
                    "bored":{'emo':['anim_bored_01','anim_bored_02','anim_bored_event_01','anim_driving_upset_start_01']}}

    buildingMaps = {}
    coins = 0
    lights_on = []
    turned_lights_on_this_time = False
    currentLights = [None,None,None,None]
    lights = {CColors[0]: Colors.GREEN, CColors[1]: Colors.RED, CColors[2]: Colors.BLUE, CColors[3]: Colors.YELLOW, CColors[4]: Colors.MAGENTA}
    penalised_this_time = False
    got_this_time = []
    pizza_queue = []
    can_have_icecream = True;

    def __init__(self, coz):
        self.cozmo = coz

        self.define_custom_objects();

        self.action_queue = []

        self.lift_up = 0
        self.lift_down = 0
        self.head_up = 0
        self.head_down = 0

        self.text_to_say = ""

        self.anims_for_keys = ["bored",  # 1
                                  "sad",  # 2
                                  "happy",  # 3
                               "icecream", #4
                                 ]
        self.cozmo.set_lift_height(0,in_parallel=True);
        self.cozmo.set_head_angle(cozmo.robot.MAX_HEAD_ANGLE/8,in_parallel=True)

        self.visible_objects = []
        self.measuring_dist = False;

        _thread.start_new_thread(self.start_Pizza_Thread, ())

        self.cubes = None
        try:
            self.cubes = self.cozmo.world.wait_until_observe_num_objects(1, object_type = cozmo.objects.LightCube,timeout=10)
        except asyncio.TimeoutError:
            print("Didn't find a cube :-(")
            return
        finally:
            if len(self.cubes) > 0:
                self.cozmo.camera.image_stream_enabled = True;
                self.cubes[0].set_lights_off();
                self.cozmo.set_head_angle(cozmo.util.Angle(degrees=30),in_parallel=True);
                self.cozmo.world.add_event_handler(cozmo.objects.EvtObjectAppeared, self.on_object_appeared)
                self.cozmo.world.add_event_handler(cozmo.objects.EvtObjectDisappeared, self.on_object_disappeared)

            else:
                print("Not found");


    def start_Pizza_Thread(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.pizzaSpawning())

    async def pizzaSpawning(self):
        rndnum = random.randint(0, 3);
        if rndnum not in self.pizza_queue and len(self.pizza_queue) < 4:
            self.pizza_queue.append(rndnum);
        rndTime = random.randint(10,60);
        await asyncio.sleep(rndTime);
        await self.pizzaSpawning();

    async def measure_distance_visible_objects(self):
        while True:
            for obj in self.visible_objects:
                dist = self.robots_distance_to_object(self.cozmo, obj);
                current_building = self.buildingMaps[obj.object_type];
                if current_building == Shop:
                    if(dist < 400):
                        if len(self.pizza_queue) == 0:
                            continue;
                        for pizza in self.pizza_queue:
                            self.light_cube(pizza);
                        self.pizza_queue = []
                elif current_building in CColors:
                    if (dist < 400):
                        if current_building in self.lights_on:
                            self.got_this_time.append(current_building);
                            self.correct_house_reached(current_building);
                        elif current_building not in self.got_this_time:
                            self.incorrect_house_reached();
                elif current_building == Icecream:
                    if dist < 400 and self.can_have_icecream and self.coins > 0:
                        self.can_have_icecream = False;
                        asyncio.ensure_future(self.icecream_reached());
            await asyncio.sleep(0.5);

    async def icecream_reached(self):
        self.coins -= 1;
        if self.coins < 0:
            self.coins = 0;
        back_pack_lights = [None, None, None]
        for i in range(0, self.coins):
            if i % 2 == 0:
                back_pack_lights[int(i / 2)] = Colors.GRAY
            else:
                back_pack_lights[int(i / 2)] = Colors.WHITE
        self.cozmo.set_backpack_lights(None, back_pack_lights[0], back_pack_lights[1], back_pack_lights[2], None);
        await self.cozmo.say_text("Yummy").wait_for_completed();
        anim_name = self.key_code_to_anim_name(ord('4'))
        self.play_animation(anim_name)

        await asyncio.sleep(30);
        self.can_have_icecream = True;

    def correct_house_reached(self, color):
        index = self.currentLights.index(self.lights[color]);
        self.currentLights[index] = None;
        self.lights_on.remove(color);
        self.coins += 1;
        back_pack_lights = [None, None, None]
        for i in range(0, self.coins):
            if i%2 == 0:
                back_pack_lights[int(i/2)] = Colors.GRAY
            else:
                back_pack_lights[int(i/2)] = Colors.WHITE
        self.cozmo.set_backpack_lights(None, back_pack_lights[0], back_pack_lights[1], back_pack_lights[2], None);
        self.cubes[0].set_light_corners(self.currentLights[0], self.currentLights[1],self.currentLights[2], self.currentLights[3]);
        self.turned_lights_on_this_time = False;
        anim_name = self.key_code_to_anim_name(ord('3'))
        self.play_animation(anim_name)

    def incorrect_house_reached(self):
        if self.penalised_this_time == True or len(self.lights_on)==0:
            return;
        self.penalised_this_time = True;
        self.coins -= 1;
        if self.coins < 0:
            self.coins = 0;
        back_pack_lights = [None, None, None]
        for i in range(0, self.coins):
            if i%2 == 0:
                back_pack_lights[int(i/2)] = Colors.GRAY
            else:
                back_pack_lights[int(i/2)] = Colors.WHITE
        self.cozmo.set_backpack_lights(None, back_pack_lights[0], back_pack_lights[1], back_pack_lights[2], None);
        anim_name = self.key_code_to_anim_name(ord('2'))
        self.play_animation(anim_name)

    async def on_object_appeared(self, event, *, obj, **kw):
        if 'Custom' in str(type(obj)):
            self.visible_objects.append(obj);
        if(not self.measuring_dist):
            self.measuring_dist = True;
            asyncio.ensure_future(self.measure_distance_visible_objects());

    async def on_object_disappeared(self, event, *, obj, **kw):
        if obj in self.visible_objects:
            self.visible_objects.remove(obj);


    def robots_distance_to_object(self,robot, target):
        """
        Returns: The distance (mm) between the robot and the target object
        """
        object_vector = np.array((target.pose.position.x - robot.pose.position.x,
                                  target.pose.position.y - robot.pose.position.y))
        return math.sqrt((object_vector ** 2).sum())

    def joystick_start(self):
        self.cozmo.drive_wheels(0,0,0,0)

    def joystick_end(self):
        self.cozmo.drive_wheels(0,0,0,0)

    def joystick_move(self,angle,force):
        forward_speed = 50 + force*30;
        turn_speed = 30;

        if(angle > 45 and angle < 135):
            direction = "up";
        elif(angle < 45 or angle > 315):
            direction = "right";
        elif(angle > 135 and angle < 225):
            direction = "left";
        elif(angle > 225 and angle < 315):
            direction = "down";

        drive_dir = 0;
        turn_dir = 0;
        if(direction == "up"):
            drive_dir = 1;
        elif(direction == "right"):
            turn_dir = 1;
        elif(direction == "left"):
            turn_dir = -1;
        elif(direction == "down"):
            drive_dir = -1

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

    def light_cube(self,rndnum,forced=False):
        if len(self.lights_on) > 3:
            return;

        self.turned_lights_on_this_time = True;
        self.penalised_this_time = False;
        self.got_this_time = [];

        color = CColors[rndnum];
        if color not in self.lights_on:
            self.lights_on.append(color);
            for i in range(0,4):
                if self.currentLights[i] == None:
                    self.currentLights[i] = self.lights[color]
                    break;
        elif forced == True:
            index = self.currentLights.index(self.lights[color]);
            self.currentLights[index] = None;
            self.lights_on.remove(color);

        self.cubes[0].set_light_corners(self.currentLights[0], self.currentLights[1],self.currentLights[2], self.currentLights[3]);

    def handle_key(self, key_code, is_key_down):
        '''Called on any key press or release
           Holding a key down may result in repeated handle_key calls with is_key_down==True
        '''
        # Handle any keys being released (e.g. the end of a key-click)
        if not is_key_down:
            if (key_code >= ord('1')) and (key_code <= ord('3')):
                anim_name = self.key_code_to_anim_name(key_code)
                self.play_animation(anim_name)
            elif key_code == 37:
                self.light_cube(2,forced=True);
            elif key_code == 38:
                self.light_cube(1,forced=True);
            elif key_code == 39:
                self.light_cube(0,forced=True);
            elif key_code == 40:
                self.light_cube(3,forced=True);
            elif key_code == ord(' '):
                self.say_text(self.text_to_say)

    def key_code_to_anim_name(self, key_code):
        key_num = key_code - ord('1')
        anim_category = self.anims_for_keys[key_num]
        category_arr = self.reactionDict[anim_category]['emo']
        anim_name = random.choice (category_arr)
        return anim_name

    def reset_head_position(self, angle):
        try:
            self.cozmo.set_head_angle(cozmo.util.Angle(degrees=angle));
            return True
        except cozmo.exceptions.RobotBusy:
            return False

    def say_text(self, text_to_say):
        self.queue_action((self.try_say_text, text_to_say))
        self.update()

    def play_animation(self, anim_name):
        self.queue_action((self.try_play_anim, anim_name))
        self.update()
        self.queue_action((self.reset_head_position, 30))
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

    def define_custom_objects(self):

        self.buildingMaps[CustomObjectTypes.CustomType09] = Shop;
        self.buildingMaps[CustomObjectTypes.CustomType02] = CColors[0];
        self.buildingMaps[CustomObjectTypes.CustomType14] = CColors[1];
        self.buildingMaps[CustomObjectTypes.CustomType16] = CColors[2];
        self.buildingMaps[CustomObjectTypes.CustomType04] = CColors[3];
        self.buildingMaps[CustomObjectTypes.CustomType15] = CColors[4];
        self.buildingMaps[CustomObjectTypes.CustomType07] = Icecream;

        self.buildingMaps[CustomObjectTypes.CustomType03] = 'n';
        self.buildingMaps[CustomObjectTypes.CustomType05] = 'o';
        self.buildingMaps[CustomObjectTypes.CustomType06] = 'i';
        self.buildingMaps[CustomObjectTypes.CustomType08] = 's';
        self.buildingMaps[CustomObjectTypes.CustomType10] = 'r';
        self.buildingMaps[CustomObjectTypes.CustomType11] = 'd';
        self.buildingMaps[CustomObjectTypes.CustomType12] = 'l';
        self.buildingMaps[CustomObjectTypes.CustomType13] = 'c';

        self.buildingMaps[CustomObjectTypes.CustomType17] = 'e';


        cube_obj_1 = self.cozmo.world.define_custom_cube(CustomObjectTypes.CustomType02,
                                                  CustomObjectMarkers.Diamonds2,
                                                  100,
                                                  90, 90, False)
        cube_obj_2 = self.cozmo.world.define_custom_cube(CustomObjectTypes.CustomType03,
                                                             CustomObjectMarkers.Diamonds3,
                                                             100,
                                                             90, 90, True)
        cube_obj_3 = self.cozmo.world.define_custom_cube(CustomObjectTypes.CustomType04,
                                                             CustomObjectMarkers.Diamonds4,
                                                             100,
                                                             90, 90, True)
        cube_obj_4 = self.cozmo.world.define_custom_cube(CustomObjectTypes.CustomType05,
                                                             CustomObjectMarkers.Diamonds5,
                                                             100,
                                                             90, 90, True)

        cube_obj_5 = self.cozmo.world.define_custom_cube(CustomObjectTypes.CustomType06,
                                                             CustomObjectMarkers.Circles2,
                                                             100,
                                                             90, 90, True)
        cube_obj_6 = self.cozmo.world.define_custom_cube(CustomObjectTypes.CustomType07,
                                                             CustomObjectMarkers.Circles3,
                                                             100,
                                                             90, 90, True)
        cube_obj_7 = self.cozmo.world.define_custom_cube(CustomObjectTypes.CustomType08,
                                                             CustomObjectMarkers.Circles4,
                                                             100,
                                                             90, 90, True)
        cube_obj_8 = self.cozmo.world.define_custom_cube(CustomObjectTypes.CustomType09,
                                                             CustomObjectMarkers.Circles5,
                                                             100,
                                                             90, 90, True)

        cube_obj_9 = self.cozmo.world.define_custom_cube(CustomObjectTypes.CustomType10,
                                                             CustomObjectMarkers.Triangles2,
                                                             100,
                                                             90, 90, True)
        cube_obj_10 = self.cozmo.world.define_custom_cube(CustomObjectTypes.CustomType11,
                                                             CustomObjectMarkers.Triangles3,
                                                             100,
                                                             90, 90, True)
        cube_obj_11 = self.cozmo.world.define_custom_cube(CustomObjectTypes.CustomType12,
                                                             CustomObjectMarkers.Triangles4,
                                                             100,
                                                             90, 90, True)
        cube_obj_12 = self.cozmo.world.define_custom_cube(CustomObjectTypes.CustomType13,
                                                             CustomObjectMarkers.Triangles5,
                                                             100,
                                                             90, 90, True)

        cube_obj_13 = self.cozmo.world.define_custom_cube(CustomObjectTypes.CustomType14,
                                                             CustomObjectMarkers.Hexagons2,
                                                             100,
                                                             90, 90, True)
        cube_obj_14 = self.cozmo.world.define_custom_cube(CustomObjectTypes.CustomType15,
                                                             CustomObjectMarkers.Hexagons3,
                                                             100,
                                                             90, 90, True)
        cube_obj_15 = self.cozmo.world.define_custom_cube(CustomObjectTypes.CustomType16,
                                                             CustomObjectMarkers.Hexagons4,
                                                             100,
                                                             90, 90, True)
        cube_obj_16 = self.cozmo.world.define_custom_cube(CustomObjectTypes.CustomType17,
                                                             CustomObjectMarkers.Hexagons5,
                                                             100,
                                                             90, 90, True)
@flask_app.route("/")
def handle_index_page():
    return '''
    <html>
        <head>
            <title>remote_control_cozmo.py display</title>
            <link type="text/css" rel="stylesheet" href="static/styles.css"/>
            <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
            <script src="static/dist/nipplejs.js" charset="utf-8"></script>
        </head>
        <body class="unselectable">
            <h1 style="text-align:center">Cozmo World</h1>
            <div id="left"></div>
            <div id="right"></div>
            <table>
                <tr>
                    <td width=5%></td>
                    <td style="text-align:center;" valign=top>
                        <h2>Control Movement</h2>
                    </td>
                    <td width=40%></td>
                    <td style="text-align:center;" valign=top>
                        <h2 id="headLiftText">Control Lift</h2>
                    </td>
                </tr>
                <tr>
                    <td width=5%></td>
                    <td>
                        <div style="text-align:center;width:100%;">
                          <button class="unselectable" style="height:80px;width:150px" ontouchstart="moveup()" onmousedown="moveup()" onmouseup="stopMove()" ontouchend="stopMove()"><img src="static/images/up.png" height="100%"></button><br><br><br>
                          <button class="unselectable" style="height:80px;width:150px" ontouchstart="moveleft()" onmousedown="moveleft()" onmouseup="stopMove()"  ontouchend="stopMove()"><img src="static/images/left.png" height="100%"></button>
                          &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
                          <button class="unselectable" style="height:80px;width:150px" ontouchstart="moveright()" onmousedown="moveright()" onmouseup="stopMove()"  ontouchend="stopMove()"><img src="static/images/right.png" height="100%"></button><br><br><br>
                          <button class="unselectable" style="height:80px;width:150px" ontouchstart="movedown()" onmousedown="movedown()" onmouseup="stopMove()" ontouchend="stopMove()"><img src="static/images/down.png" height="100%"></button>
                        </div>
                    </td>
                    <td width=40%></td>
                    <td>
                        <div style="text-align:center;width:100%;">
                          <button class="unselectable" style="height:80px;width:150px" ontouchstart="moveupLift()" onmousedown="moveupLift()" onmouseup="stopMoveLift()" ontouchend="stopMove()" ><img src="static/images/up.png" height="100%"></button><br><br><br><br>
                          <button class="unselectable" style="height:80px;width:150px;" ontouchstart="movedownLift()" onmousedown="movedownLift()" onmouseup="stopMoveLift()" ontouchend="stopMove()"><img src="static/images/down.png" height="100%"></button>
                        </div>
                    </td>

                </tr>
            </table>

            <script type="text/javascript">
                var gisControllingHead = false

                function moveup() {
                    angle = 90;
                    force = 1;
                    postHttpRequest("joystickMove", {angle,force})
                }
                function movedown() {
                    angle = 270;
                    force = 1;
                    postHttpRequest("joystickMove", {angle,force})
                }
                function moveleft() {
                    angle = 180;
                    force = 1;
                    postHttpRequest("joystickMove", {angle,force})
                }
                function moveright() {
                    angle = 0;
                    force = 1;
                    postHttpRequest("joystickMove", {angle,force})
                }
                function stopMove() {
                    msg = "End";
                    postHttpRequest("joystickEnd", {msg})
                }

                function moveupLift() {
                    angle = 90;
                    force = 1;
                    postHttpRequest("liftMove", {angle,force})
                }
                function movedownLift() {
                    angle = 270;
                    force = 1;
                    postHttpRequest("liftMove", {angle,force})
                }
                function stopMoveLift() {
                    msg = "End";
                    postHttpRequest("liftEnd", {msg})
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
    cozmo.robot.Robot.drive_off_charger_on_connect = True  # RC can drive off charger if required
    try:
        cozmo.connect_with_tkviewer(run)
    except cozmo.ConnectionError as e:
        sys.exit("A connection error occurred: %s" % e)
