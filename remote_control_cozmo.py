#!/usr/bin/env python3

# Copyright (c) 2016 Anki, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License")
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
from cozmo.util import distance_mm, speed_mmps
from pygame import mixer
import _thread
import cozmo
import math
import random
import asyncio
import numpy as np
import time
from cozmo.objects import CustomObjectMarkers, CustomObjectTypes
from Arcade import Arcade
from Patrol.patrol import Patrol
from merry_go_round import MerryGoRound
from MemCapture import MemCapture

try:
    from flask import Flask, request, render_template
except ImportError:
    sys.exit("Cannot import from flask: Do `pip3 install --user flask` to install")

try:
    from PIL import Image, ImageDraw
except ImportError:
    sys.exit("Cannot import from PIL: Do `pip3 install --user Pillow` to install")


flask_app = Flask(__name__)
remote_control_cozmo = None

CColors = ["Green", "Red", "Blue", "Yellow", "Magenta"]
CShop = "Shop"
CIcecream = "Icecream"
CStatue = "Statue"
CArcade = "Arcade"
CGarage = "Garage"
CMerryGoRound = "MGR"

TIMER_1 = 90
TIMER_2 = 120
TIMER_3 = 150
pizzaSpawned = False

class RemoteControlCozmo:
    reactionDict = {"happy":{'emo':['anim_memorymatch_solo_successgame_player_01','anim_memorymatch_successhand_cozmo_02','anim_reacttoblock_success_01','anim_fistbump_success_01']},
                    "sad":{'emo':['anim_memorymatch_failgame_cozmo_03','anim_keepaway_losegame_02','anim_reacttoblock_frustrated_01','anim_reacttoblock_frustrated_int2_01']},
                    "icecream": {'emo': ['anim_greeting_happy_01','anim_greeting_happy_03','anim_memorymatch_successhand_cozmo_04']},
                    "bored":{'emo':['anim_bored_01','anim_bored_02','anim_bored_event_01','anim_driving_upset_start_01']},
                    "laugh":{'emo':['id_poked_giggle','anim_fistbump_success_01']}}

    audioEffects = {"idle":[cozmo.anim.Triggers.OnboardingSoundOnlyLiftEffortPickup,cozmo.anim.Triggers.OnboardingSoundOnlyLiftEffortPlaceLow,cozmo.anim.Triggers.SoundOnlyLiftEffortPickup,cozmo.anim.Triggers.SoundOnlyLiftEffortPlaceHigh,cozmo.anim.Triggers.SoundOnlyLiftEffortPlaceLow,cozmo.anim.Triggers.SoundOnlyLiftEffortPlaceRoll,cozmo.anim.Triggers.SoundOnlyTurnSmall]}
    reverse_audio = 'anim_explorer_drvback_loop_01'
    ting = 'anim_cozmosays_getin_short_01'

    arcadeGame = None
    autonomousInstance = None
    merrygoround = None
    instagram = None;

    buildingMaps = {}
    coins = 0
    lights_on = []
    turned_lights_on_this_time = False
    currentLights = [None,None,None,None]
    lights = {CColors[0]: Colors.GREEN, CColors[1]: Colors.RED, CColors[2]: Colors.BLUE, CColors[3]: Colors.YELLOW, CColors[4]: Colors.MAGENTA}
    lights_1 = {CColors[0]: Colors.GREEN_1, CColors[1]: Colors.RED_1, CColors[2]: Colors.BLUE_1, CColors[3]: Colors.YELLOW_1, CColors[4]: Colors.MAGENTA_1}
    lights_2 = {CColors[0]: Colors.GREEN_2, CColors[1]: Colors.RED_2, CColors[2]: Colors.BLUE_2, CColors[3]: Colors.YELLOW_2, CColors[4]: Colors.MAGENTA_2}
    penalised_this_time = False
    got_this_time = []
    pizza_queue = []
    can_have_icecream = True
    can_see_statue = True
    can_see_arcade = True
    can_see_ride = True
    checkForRideEnd = False

    played_laugh_anim = False

    dizzy_level = 0
    update_dizzy_count = 0

    is_autonomous_mode = True
    is_auto_switch_on = False
    is_moving = False
    l_wheel_speed = 0
    r_wheel_speed = 0

    def __init__(self, coz):
        self.cozmo = coz
        self.arcadeGame = Arcade(self.cozmo, self)
        self.autonomousInstance = Patrol(self,self.cozmo)
        self.merrygoround = MerryGoRound(self.cozmo, self)
        self.instagram = MemCapture(self.cozmo,self);

        self.define_custom_objects()

        self.action_queue = []

        self.lift_up = 0
        self.lift_down = 0
        self.head_up = 0
        self.head_down = 0

        self.text_to_say = ""
        self.cozmo_audio_effect_interval = random.randint(200,1000)
        self.update_count = 0

        self.anims_for_keys = ["bored",  # 1
                                  "sad",  # 2
                                  "happy",  # 3
                               "icecream", #4
                               "laugh" #5
                                 ]

        self.cozmo.set_lift_height(0,in_parallel=True)
        self.cozmo.set_head_angle(cozmo.util.Angle(degrees=-15),in_parallel=True).wait_for_completed()

        self.visible_objects = []
        self.measuring_dist = False

        _thread.start_new_thread(self.start_Pizza_Thread, ())

        self.cubes = None
        try:
            self.cubes = self.cozmo.world.wait_until_observe_num_objects(1, object_type = cozmo.objects.LightCube,timeout=10)
        except asyncio.TimeoutError:
            print("Didn't find a cube :-(")
            return
        finally:
            # for cube in self.cubes:
            #     cube.set_lights(Colors.BLUE)
            if len(self.cubes) > 0:
                self.cozmo.camera.image_stream_enabled = True
                self.cubes[0].set_lights_off()
                self.cozmo.drive_straight(distance_mm(10), speed_mmps(50), in_parallel=True).wait_for_completed()
                self.cozmo.set_head_angle(cozmo.util.Angle(degrees=30),in_parallel=True)
                self.cozmo.world.add_event_handler(cozmo.objects.EvtObjectAppeared, self.on_object_appeared)
                self.cozmo.world.add_event_handler(cozmo.objects.EvtObjectDisappeared, self.on_object_disappeared)
            else:
                print("Not found")


    def start_Pizza_Thread(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.pizzaSpawning())

    async def pizzaSpawning(self):
        global pizzaSpawned

        rndTime = random.randint(10, 20)
        await asyncio.sleep(rndTime)

        rndnum = random.randint(0, 4)

        if rndnum not in self.pizza_queue and len(self.pizza_queue) < 4 and self.can_see_arcade:
            print("PIZZA SPAWNED")
            pizzaSpawned = True
            self.pizza_queue.append({'time':time.time(), 'pizza':rndnum})

        rndTime = random.randint(0,90)
        await asyncio.sleep(rndTime)

        await self.pizzaSpawning()

    async def measure_distance_visible_objects(self):
        while True:
            for obj in self.visible_objects:
                dist = self.robots_distance_to_object(self.cozmo, obj)
                current_building = self.buildingMaps[obj.object_type]
                if current_building == CShop:
                    if (dist < 500 or (self.is_autonomous_mode and dist < 1000)):
                        if len(self.pizza_queue) == 0:
                            continue
                        for pizza in self.pizza_queue:
                            self.light_cube(pizza)
                        self.pizza_queue = []
                        if self.autonomousInstance:
                            await self.autonomousInstance.onReactiveAnimationFinished()
                elif current_building in CColors:
                    if (dist < 500 or (self.is_autonomous_mode and dist < 1000)):
                        if self.is_color_in_lights_on(current_building):
                            self.got_this_time.append(current_building)
                            await self.correct_house_reached(current_building)
                        elif current_building not in self.got_this_time:
                            await self.incorrect_house_reached()
                elif current_building == CIcecream:
                    if dist < 500 and self.can_have_icecream:
                        if self.coins > 0:
                            self.can_have_icecream = False
                            asyncio.ensure_future(self.icecream_reached())
                        else:
                            anim_name = self.key_code_to_anim_name(ord('2'))
                            self.play_animation(anim_name)
                elif current_building == CStatue and not self.is_autonomous_mode:
                    if dist < 600 and self.can_see_statue:
                        self.can_see_statue = False
                        asyncio.ensure_future(self.statue_reached())
                elif current_building == CGarage:
                    if self.is_auto_switch_on:
                        asyncio.ensure_future(self.start_autonomous_mode())
                elif current_building == CArcade:
                    if dist < 800 and self.can_see_arcade:
                        if self.coins > 0:
                            self.can_see_arcade = False
                            asyncio.ensure_future(self.arcade_reached())
                        else:
                            anim_name = self.key_code_to_anim_name(ord('2'))
                            self.play_animation(anim_name)
                elif current_building == CMerryGoRound:
                    if dist < 600 and self.can_see_ride:
                        if self.coins > 1:
                            self.can_see_ride = False
                            asyncio.ensure_future(self.ride_reached())
                        else:
                            anim_name = self.key_code_to_anim_name(ord('2'))
                            self.play_animation(anim_name)

            await asyncio.sleep(0.5)

    async def ride_reached(self):
        self.coins -= 2
        if self.coins < 0:
            self.coins = 0
        back_pack_lights = [None, None, None]
        for i in range(0, self.coins):
            if i % 2 == 0:
                back_pack_lights[int(i / 2)] = Colors.GRAY
            else:
                back_pack_lights[int(i / 2)] = Colors.WHITE
        self.cozmo.set_backpack_lights(None, back_pack_lights[0], back_pack_lights[1], back_pack_lights[2], None)

        self.is_autonomous_mode = True
        await self.cozmo.drive_wheels(0, 0, 0, 0)

        await self.merrygoround.start_experience()

    async def clickPicture(self):
        asyncio.ensure_future(self.instagram.start_program());

    async def ride_started(self):
        asyncio.ensure_future(self.instagram.start_program());
        await asyncio.sleep(10);
        await self.ride_end()

    async def ride_end(self):
        self.is_autonomous_mode = False
        self.checkForRideEnd = True
        await asyncio.sleep(120)
        self.can_see_ride = True


    async def start_autonomous_mode(self):
        self.is_autonomous_mode = True
        await self.autonomousInstance.start(self.cozmo)

    async def memory_captured(self):
        print("MEMORY CAPTURED");

    async def arcade_reached(self):
        self.coins -= 1
        if self.coins < 0:
            self.coins = 0
        back_pack_lights = [None, None, None]
        for i in range(0, self.coins):
            if i % 2 == 0:
                back_pack_lights[int(i / 2)] = Colors.GRAY
            else:
                back_pack_lights[int(i / 2)] = Colors.WHITE
        self.cozmo.set_backpack_lights(None, back_pack_lights[0], back_pack_lights[1], back_pack_lights[2], None)

        self.is_autonomous_mode = True
        await self.cozmo.drive_wheels(0, 0, 0, 0)

        await self.arcadeGame.startArcadeGame()

    async def arcadeGameEnd(self):
        self.is_autonomous_mode = False
        await asyncio.sleep(10)
        self.can_see_arcade = True
        self.arcadeGame = None
        self.arcadeGame = Arcade(self.cozmo, self)

    async def statue_reached(self):
        anim_done = False;
        while anim_done is False:
            try:
                await self.cozmo.play_anim(self.ting).wait_for_completed()
                anim_done = True
            except cozmo.exceptions.RobotBusy:
                await asyncio.sleep(0.1);

        anim_done = False;
        while anim_done is False:
            try:
                await self.cozmo.set_lift_height(1.0, duration=0.1, in_parallel=True).wait_for_completed()
                anim_done = True
            except cozmo.exceptions.RobotBusy:
                await asyncio.sleep(0.1);

        anim_done = False;
        while anim_done is False:
            try:
                await self.cozmo.say_text("oh, Cozmo", duration_scalar=2).wait_for_completed()
                anim_done = True
            except cozmo.exceptions.RobotBusy:
                await asyncio.sleep(0.1);

        anim_done = False;
        while anim_done is False:
            try:
                await self.cozmo.set_lift_height(0.0, duration=0.1, in_parallel=True).wait_for_completed()
                anim_done = True
            except cozmo.exceptions.RobotBusy:
                await asyncio.sleep(0.1);

        self.queue_action((self.reset_head_position, 30))

        await asyncio.sleep(60)
        self.can_see_statue = True

    async def icecream_reached(self):
        self.coins -= 1
        if self.coins < 0:
            self.coins = 0
        back_pack_lights = [None, None, None]
        for i in range(0, self.coins):
            if i % 2 == 0:
                back_pack_lights[int(i / 2)] = Colors.GRAY
            else:
                back_pack_lights[int(i / 2)] = Colors.WHITE
        self.cozmo.set_backpack_lights(None, back_pack_lights[0], back_pack_lights[1], back_pack_lights[2], None)
        anim_name = self.key_code_to_anim_name(ord('4'))
        self.play_animation(anim_name)
        self.say_text("Yummy")

        await asyncio.sleep(30)
        self.can_have_icecream = True

    async def correct_house_reached(self, color):
        l_index = self.idex_of_color_in_lights_on(color)
        index = self.currentLights.index(self.lights_on[l_index]['light'])
        self.currentLights[index] = None
        for item in self.lights_on:
            if item['color'] == color:
                self.lights_on.remove(item)
                break
        self.coins += 1
        back_pack_lights = [None, None, None]
        for i in range(0, self.coins):
            if i%2 == 0:
                back_pack_lights[int(i/2)] = Colors.GRAY
            else:
                back_pack_lights[int(i/2)] = Colors.WHITE
        self.cozmo.set_backpack_lights(None, back_pack_lights[0], back_pack_lights[1], back_pack_lights[2], None)
        self.cubes[0].set_light_corners(self.currentLights[0], self.currentLights[1],self.currentLights[2], self.currentLights[3])
        self.turned_lights_on_this_time = False

        if self.is_autonomous_mode:
            if self.autonomousInstance:
                await self.play_correct_anim_autonomous()
                await self.autonomousInstance.onReactiveAnimationFinished()
        else:
            anim_name = self.key_code_to_anim_name(ord('3'))
            self.play_animation(anim_name)

    async def play_correct_anim_autonomous(self):
        try:
            anim_name = 'anim_reacttoblock_success_01'
            await self.cozmo.play_anim(name=anim_name).wait_for_completed()
            await self.cozmo.drive_straight(distance_mm(2), speed_mmps(50)).wait_for_completed()
        except cozmo.exceptions.RobotBusy:
            await asyncio.sleep(0.5)
            await self.play_correct_anim_autonomous()

    async def incorrect_house_reached(self):
        if self.penalised_this_time == True or len(self.lights_on)==0:
            return
        self.penalised_this_time = True
        self.coins -= 1
        if self.coins < 0:
            self.coins = 0
        back_pack_lights = [None, None, None]
        for i in range(0, self.coins):
            if i%2 == 0:
                back_pack_lights[int(i/2)] = Colors.GRAY
            else:
                back_pack_lights[int(i/2)] = Colors.WHITE
        self.cozmo.set_backpack_lights(None, back_pack_lights[0], back_pack_lights[1], back_pack_lights[2], None)
        anim_name = self.key_code_to_anim_name(ord('2'))
        self.play_animation(anim_name)

    async def on_object_appeared(self, event, *, obj, **kw):
        if 'Custom' in str(type(obj)):
            self.visible_objects.append(obj)
        if(not self.measuring_dist):
            self.measuring_dist = True
            asyncio.ensure_future(self.measure_distance_visible_objects())

    async def on_object_disappeared(self, event, *, obj, **kw):
        if obj in self.visible_objects:
            self.visible_objects.remove(obj)

    def robots_distance_to_object(self,robot, target):
        """
        Returns: The distance (mm) between the robot and the target object
        """
        object_vector = np.array((target.pose.position.x - robot.pose.position.x,
                                  target.pose.position.y - robot.pose.position.y))
        return math.sqrt((object_vector ** 2).sum())

    def joystick_end(self):
        self.is_moving = False
        self.l_wheel_speed = 0
        self.r_wheel_speed = 0
        self.cozmo.drive_wheels(self.l_wheel_speed, self.r_wheel_speed, self.l_wheel_speed * 4, self.r_wheel_speed * 4)

    def joystick_move(self,angle,force):
        if self.is_autonomous_mode:
            return

        if self.checkForRideEnd is True:
            self.checkForRideEnd = False;
            self.dizzy_level = self.merrygoround.end_experience()
            self.queue_action((self.reset_head_position, 30))


        # forward_speed = 50 + force*30
        forward_speed = 50
        turn_speed = 30

        if(angle > 45 and angle < 135):
            direction = "up"
        elif(angle < 45 or angle > 315):
            direction = "right"
        elif(angle > 135 and angle < 225):
            direction = "left"
        elif(angle > 225 and angle < 315):
            direction = "down"

        drive_dir = 0
        turn_dir = 0
        if(direction == "up"):
            drive_dir = 1
            self.is_moving = True
        elif(direction == "right"):
            turn_dir = 1
        elif(direction == "left"):
            turn_dir = -1
        elif(direction == "down"):
            self.is_moving = True
            drive_dir = -1

        self.l_wheel_speed = (drive_dir * forward_speed) + (turn_speed * turn_dir)
        self.r_wheel_speed = (drive_dir * forward_speed) - (turn_speed * turn_dir)

        if drive_dir == -1:
            self.try_play_anim(self.reverse_audio)

        self.cozmo.drive_wheels(self.l_wheel_speed, self.r_wheel_speed, self.l_wheel_speed*4, self.r_wheel_speed*4)


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

    def try_play_anim_trigger(self, anim_trigger):
        try:
            self.cozmo.play_anim_trigger(anim_trigger)
            return True
        except cozmo.exceptions.RobotBusy:
            return False

    def light_cube(self,pizza,forced=False):
        if len(self.lights_on) > 3:
            return

        self.turned_lights_on_this_time = True
        self.penalised_this_time = False
        self.got_this_time = []

        color = CColors[pizza['pizza']]
        if not self.is_color_in_lights_on(color):
            for i in range(0,4):
                if self.currentLights[i] == None:
                    self.lights_on.append({'color': color, 'time': pizza['time'], 'light': self.lights[color]})
                    self.currentLights[i] = self.lights[color]
                    break
        elif forced == True:
            index = self.currentLights.index(self.lights[color])
            self.currentLights[index] = None
            for item in self.lights_on:
                if item['color']==color:
                    self.lights_on.remove(item)
                    break

        print("setting light cube corners")
        self.cubes[0].set_light_corners(self.currentLights[0], self.currentLights[1],self.currentLights[2], self.currentLights[3])
        print(self.currentLights)

    def is_color_in_lights_on(self,color):
        for item in self.lights_on:
            if item['color'] == color:
                return True
        return False

    def idex_of_color_in_lights_on(self,color):
        i = 0
        for item in self.lights_on:
            if item['color'] == color:
                return i
            i += 1
        return -1

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
                self.light_cube({'time':time.time(), 'pizza':2},forced=True)
            elif key_code == 38:
                self.light_cube({'time':time.time(), 'pizza':1},forced=True)
            elif key_code == 39:
                self.light_cube({'time':time.time(), 'pizza':0},forced=True)
            elif key_code == 40:
                self.light_cube({'time':time.time(), 'pizza':3},forced=True)
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
            self.cozmo.set_head_angle(cozmo.util.Angle(degrees=angle))
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

        if not self.can_see_arcade:
            return

        if self.dizzy_level != 0:
            self.update_dizzy_count += 1
            if self.played_laugh_anim is False:
                self.played_laugh_anim = True
                anim_name = self.key_code_to_anim_name(ord('5'))
                self.play_animation(anim_name)
            if self.update_dizzy_count == 100:
                self.played_laugh_anim = False
                self.update_dizzy_count = 0
                self.dizzy_level = self.dizzy_level - 1

        if self.is_moving:
            if self.l_wheel_speed > 0:
                self.l_wheel_speed += 1
                self.r_wheel_speed += 1
            elif self.l_wheel_speed < 0:
                self.l_wheel_speed -= 1
                self.r_wheel_speed -= 1

            lmultiplier = 0
            rmultiplier = 0

            if self.dizzy_level != 0:
                rmultiplier = self.dizzy_level * random.randint(-50, 50)
                lmultiplier = self.dizzy_level * random.randint(-50, 50)

            self.cozmo.drive_wheels(self.l_wheel_speed+rmultiplier, self.r_wheel_speed+lmultiplier, self.l_wheel_speed * 4, self.r_wheel_speed * 4)

        self.update_count += 1
        if self.update_count == self.cozmo_audio_effect_interval:
            self.cozmo_audio_effect_interval = random.randint(200,1000)
            self.update_count = 0
            self.try_play_anim_trigger(self.audioEffects['idle'][random.randint(0,len(self.audioEffects['idle'])-1)])

        if not self.is_autonomous_mode:
            for light in self.lights_on:
                elapsed = time.time() - light['time']
                if elapsed > TIMER_3:
                    index = self.currentLights.index(light['light'])
                    self.currentLights[index] = None
                    for item in self.lights_on:
                        if item['color'] == light['color']:
                            self.lights_on.remove(item)
                            break
                    self.cubes[0].set_light_corners(self.currentLights[0], self.currentLights[1], self.currentLights[2], self.currentLights[3])
                elif elapsed > TIMER_2:
                    if light['light'] == self.lights_1[light['color']]:
                        continue
                    index = self.currentLights.index(light['light'])
                    light['light'] = self.lights_1[light['color']]
                    self.currentLights[index] = self.lights_1[light['color']]
                    self.cubes[0].set_light_corners(self.currentLights[0], self.currentLights[1], self.currentLights[2], self.currentLights[3])
                elif elapsed > TIMER_1:
                    if light['light'] == self.lights_2[light['color']]:
                        continue
                    index = self.currentLights.index(light['light'])
                    light['light'] = self.lights_2[light['color']]
                    self.currentLights[index] = self.lights_2[light['color']]
                    self.cubes[0].set_light_corners(self.currentLights[0], self.currentLights[1], self.currentLights[2], self.currentLights[3])


    def update_lift(self, up_or_down):
        if self.is_autonomous_mode:
            return
        lift_speed = 2
        lift_vel = up_or_down * lift_speed
        self.cozmo.move_lift(lift_vel)


    def update_head(self, up_or_down):
        head_speed = 1
        head_vel = up_or_down * head_speed
        self.cozmo.move_head(head_vel)

    def modechange(self, is_autonomous):
        self.is_auto_switch_on = is_autonomous
        if not self.is_auto_switch_on:
            self.is_autonomous_mode = False
            self.autonomousInstance.disableAuto()
            self.queue_action((self.reset_head_position, 30))
        else:
            print("mode change to Auto")
            self.autonomousInstance.enableAuto()

    def define_custom_objects(self):

        self.buildingMaps[CustomObjectTypes.CustomType09] = CShop
        self.buildingMaps[CustomObjectTypes.CustomType02] = CColors[0]
        self.buildingMaps[CustomObjectTypes.CustomType14] = CColors[1]
        self.buildingMaps[CustomObjectTypes.CustomType16] = CColors[2]
        self.buildingMaps[CustomObjectTypes.CustomType04] = CColors[3]
        self.buildingMaps[CustomObjectTypes.CustomType15] = CColors[4]
        self.buildingMaps[CustomObjectTypes.CustomType07] = CIcecream
        self.buildingMaps[CustomObjectTypes.CustomType11] = CStatue
        self.buildingMaps[CustomObjectTypes.CustomType13] = CArcade
        self.buildingMaps[CustomObjectTypes.CustomType08] = CGarage
        self.buildingMaps[CustomObjectTypes.CustomType10] = CMerryGoRound

        self.buildingMaps[CustomObjectTypes.CustomType03] = 'n'
        self.buildingMaps[CustomObjectTypes.CustomType05] = 'o'
        self.buildingMaps[CustomObjectTypes.CustomType06] = 'i'
        self.buildingMaps[CustomObjectTypes.CustomType17] = 'd'
        self.buildingMaps[CustomObjectTypes.CustomType12] = 'l'



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
    return render_template("index.html")

@flask_app.route('/updateCozmo', methods=['POST'])
def handle_updateCozmo():
    '''Called very frequently from Javascript to provide an update loop'''
    if remote_control_cozmo:
        remote_control_cozmo.update()
    return ""

@flask_app.route('/checkPizzaSpawn', methods=['POST'])
def handle_test():
    global pizzaSpawned
    if pizzaSpawned:
        pizzaSpawned = False
        return "true"
    return "false"

@flask_app.route('/checkMode', methods=['POST'])
def handle_mode_check():
    if remote_control_cozmo:
        return str(remote_control_cozmo.is_autonomous_mode)
    return False

@flask_app.route('/checkTips', methods=['POST'])
def handle_tips_check():
    if remote_control_cozmo:
        return str(remote_control_cozmo.coins)
    return 0

@flask_app.route('/sayText', methods=['POST'])
def handle_sayText():
    '''Called from Javascript whenever the saytext text field is modified'''
    message = json.loads(request.data.decode("utf-8"))
    if remote_control_cozmo:
        remote_control_cozmo.text_to_say = message['textEntered']
        remote_control_cozmo.try_say_text(remote_control_cozmo.text_to_say)
    return ""

@flask_app.route('/joystickMove', methods=['POST'])
def handle_joystickPosition():
    '''Called from Javascript whenever the joystick position is modified'''
    message = json.loads(request.data.decode("utf-8"))
    if remote_control_cozmo:
        remote_control_cozmo.joystick_move(message['angle'],message['force'])
    return ""

@flask_app.route('/joystickEnd', methods=['POST'])
def handle_joystickEnd():
    '''Called from Javascript whenever the joystick position is modified'''
    message = json.loads(request.data.decode("utf-8"))
    if remote_control_cozmo:
        remote_control_cozmo.joystick_end()
    return ""

@flask_app.route('/liftMove', methods=['POST'])
def handle_liftMove():
    '''Called from Javascript whenever the joystick position is modified'''
    message = json.loads(request.data.decode("utf-8"))
    if remote_control_cozmo:
        if(message['angle'] < 180):
            remote_control_cozmo.update_lift(1)
        else:
            remote_control_cozmo.update_lift(-1)
    return ""

@flask_app.route('/liftEnd', methods=['POST'])
def handle_liftEnd():
    '''Called from Javascript whenever the joystick position is modified'''
    message = json.loads(request.data.decode("utf-8"))
    if remote_control_cozmo:
        remote_control_cozmo.update_lift(0)
    return ""

@flask_app.route('/keydown', methods=['POST'])
def handle_keydown():
    '''Called from Javascript whenever a key is down (note: can generate repeat calls if held down)'''
    return handle_key_event(request, is_key_down=True)

@flask_app.route('/keyup', methods=['POST'])
def handle_keyup():
    '''Called from Javascript whenever a key is down (note: can generate repeat calls if held down)'''
    return handle_key_event(request, is_key_down=False)


@flask_app.route('/modechange', methods=['POST'])
def handle_modechange():
    message = json.loads(request.data.decode("utf-8"))
    if remote_control_cozmo:
        remote_control_cozmo.modechange(message['isRemoteMode'])
    return ""

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
    mixer.init()
    mixer.music.load('static/sounds/bg.ogg')
    mixer.music.play()

    cozmo.setup_basic_logging()
    cozmo.robot.Robot.drive_off_charger_on_connect = True  # RC can drive off charger if required
    try:
        # cozmo.connect_with_tkviewer(run)
        cozmo.connect(run)
    except cozmo.ConnectionError as e:
        sys.exit("A connection error occurred: %s" % e)
