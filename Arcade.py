import cozmo
from cozmo.util import degrees, distance_mm, speed_mmps
import time
import asyncio
import threading
import _thread
import math
from threading import Timer
from Common.woc import WOC
import random
from Common.colors import Colors



class Arcade:

    lightColors = [Colors.RED,Colors.YELLOW,Colors.GREEN]
    intensities = {100:{'emo':'sad','color':lightColors[0]},125:{'emo':'happy','color':lightColors[1]},300:{'emo':'very_happy','color':lightColors[2]}}
    arcadeCube = None
    robot = None
    direction = 1
    tapCombos = [{'speed':7,'duration':0.09},{'speed':10,'duration':0.09},{'speed':5,'duration':0.09},{'speed':3,'duration':0.1},{'speed':2,'duration':0.2},{'speed':4,'duration':0.1}]
    speed = 2
    liftThread = None
    duration = 0.1
    tapCtr = 0;
    tapped = False;
    reactionDict = {"happy" : {"emo":['anim_memorymatch_successhand_cozmo_02','anim_memorymatch_successhand_player_02','anim_rtpkeepaway_playeryes_03','anim_rtpkeepaway_playeryes_02','anim_sparking_success_01','anim_reacttoblock_ask_01','anim_reacttoblock_happydetermined_02']},
                    "very_happy":{'emo':['anim_sparking_success_02','anim_memorymatch_successhand_cozmo_04']},
                    "sad":{'emo':['anim_memorymatch_failgame_cozmo_03','anim_keepaway_losegame_02','anim_keepaway_losegame_03']}}
    curEmotion = None
    flashCtr = 0
    lights = [None,None,None,None];
    startGame = False
    flashTimerEnd = 35;
    lightFlashSpeed = 10;
    currentConfig = None;
    cubes = None
    mainInstance = None;

    def __init__(self, robot: cozmo.robot.Robot, instance):
        self.robot = robot
        self.mainInstance = instance;

    async def startArcadeGame(self):
       self.robot.stop_all_motors();

       await self.reset_head_position();

       try:
           self.cubes = await self.robot.world.wait_until_observe_num_objects(1, object_type=cozmo.objects.LightCube,
                                                                        timeout=60)
       except asyncio.TimeoutError:
           print("Didn't find a cube :-(")
           return
       finally:
           print("Cube found!!")

       if(len(self.cubes) > 0):
            self.arcadeCube = self.cubes[0]
            await self.setUpGame()

    async def reset_head_position(self):
        try:
            await self.robot.set_head_angle(cozmo.util.Angle(degrees=-10)).wait_for_completed();
        except cozmo.exceptions.RobotBusy:
            await asyncio.sleep(0.1);
            await self.reset_head_position();

    async def setUpGame(self):
        await self.robot.set_lift_height(1,10,10,0.5).wait_for_completed();

        self.arcadeCube.set_lights(Colors.BLUE);

        await self.robot.go_to_object(self.arcadeCube,cozmo.util.distance_mm(30),in_parallel=False).wait_for_completed()

        await self.robot.play_anim("anim_hiking_edgesquintgetin_01").wait_for_completed();

        self.robot.world.add_event_handler(cozmo.objects.EvtObjectTapped, self.on_object_tapped)
        self.currentConfig = random.choice(self.tapCombos)

        print(self.currentConfig['speed'])
        print(self.currentConfig['duration'])
        asyncio.ensure_future(self.tap());
        await self.changeDirection()


    async def flashLights(self):

        for i in range(0,len(self.lights)):
            self.lights[i] = None

        self.lights[self.flashCtr%4] = random.choice(self.lightColors);

        self.arcadeCube.set_light_corners(self.lights[0],self.lights[1],self.lights[2],self.lights[3]);
        self.flashCtr += 1
        if(self.flashCtr<self.flashTimerEnd):
            await asyncio.sleep(0.05 * self.flashCtr / self.lightFlashSpeed);
            await self.flashLights();
        else:
            await self.mainInstance.arcade_light_decided(self.curIntensity);
            self.tapCtr = 0;
            self.arcadeCube.set_lights(self.intensities[self.curIntensity]["color"]);
            await self.robot.drive_straight(cozmo.util.distance_mm(-40),cozmo.util.speed_mmps(50)).wait_for_completed();
            await self.react();
            await self.endGame();

    async def endGame(self):
        self.robot.move_lift(-5)
        await self.robot.play_anim('anim_fistbump_getin_01').wait_for_completed()
        await self.robot.set_head_angle(cozmo.util.Angle(degrees=30)).wait_for_completed()
        self.arcadeCube.set_light_corners(None,None,None,None);
        await self.mainInstance.arcadeGameEnd();

    async def tap(self):
        while self.tapped is False:
            self.robot.move_lift(self.currentConfig['speed'] * self.direction)
            await asyncio.sleep(0.01);

    async def changeDirection(self):
        if self.tapCtr<2:
            self.direction *= -1
            self.tapCtr += 1
            await asyncio.sleep(self.currentConfig['duration']);
            await self.changeDirection();

    async def on_object_tapped(self, event, *, obj, tap_count, tap_duration, tap_intensity, **kw):
        if self.tapped is False:
            self.tapped = True;
            self.robot.stop_all_motors();
            print(tap_intensity)
            for intensity in self.intensities.keys():
                if tap_intensity<intensity:
                    self.curIntensity = intensity
                    # self.robot.set_head_angle(cozmo.util.Angle(degrees=20))
                    # await self.mainInstance.clickPicture();
                    await self.flashLights();
                    break

    async def react(self):
        await self.robot.play_anim(random.choice(self.reactionDict[self.intensities[self.curIntensity]["emo"]]['emo'])).wait_for_completed();