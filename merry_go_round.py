import numpy as np
import cozmo
import asyncio
from PIL import Image
import _thread
import os
import random

'''
@class MerryGoRound
Play with Cozmo by spinning him aroung on a merry-go-round and watch him get dizzy.
@author - Wizards of Coz
'''

class MerryGoRound(): 
    def __init__(self, robot=None, instance=None):
        self.thresh = 5
        self.dizzy = 0      #0 = normal, 1 = tipsy, 2 = drunk, 3 = throwing up, 4 = out of order
        self.robot = robot
        self.mainInstance = instance
        self.END = False
        if self.robot is None:
            cozmo.connect(self.run)

    async def capture_values(self):
        self.acceleration = [0, 0, 0]
        while self.END is False:
            orientation = np.linalg.norm(np.floor_divide([self.robot.gyro.x, self.robot.gyro.y, self.robot.gyro.z], 1))
            if orientation > self.thresh:
                self.dizzy +=  1
            a = self.acceleration
            self.acceleration = np.floor_divide([self.robot.accelerometer.x, self.robot.accelerometer.y, self.robot.accelerometer.z], 1000)
            da = np.subtract(self.acceleration, a)
            self.da_norm = np.trunc(np.linalg.norm(da))
            if self.da_norm > self.thresh:
                self.dizzy += 1
            await asyncio.sleep(0.1)

    async def spin(self):     
        counter = 0
        while self.END is False:
            if self.robot.is_picked_up is True:
                x = random.randint(1, 4)
                if x == 1:
                    try:
                        await self.robot.play_anim_trigger(cozmo.anim.Triggers.DroneModeTurboDrivingStart).wait_for_completed()
                    except cozmo.exceptions.RobotBusy:
                        print("robot busy")
                elif x == 2:
                    try:
                        await self.robot.say_text("Faster", duration_scalar=1.2, voice_pitch=0.3).wait_for_completed()
                    except cozmo.exceptions.RobotBusy:
                        print("robot busy")
                elif x == 3:
                    try:
                        await self.robot.play_anim_trigger(cozmo.anim.Triggers.SoundOnlyRamIntoBlock).wait_for_completed()
                    except cozmo.exceptions.RobotBusy:
                        print("robot busy")
                elif x == 4:
                    try:
                        await self.robot.play_anim_trigger(cozmo.anim.Triggers.CubePounceWinHand).wait_for_completed()
                    except cozmo.exceptions.RobotBusy:
                        print("robot busy")
            await asyncio.sleep(0.1)    

    def end_experience(self):
        self.robot.abort_all_actions()
        self.END = True
        dizzy_meter = np.floor_divide(self.dizzy, 10)
        if dizzy_meter > 4:
            dizzy_meter = 4
        return dizzy_meter
        
    async def run(self, conn):
        asyncio.set_event_loop(conn._loop)
        self.robot = await conn.wait_for_robot()
        await self.start_experience()

    async def start_experience(self):
        await self.robot.set_lift_height(0).wait_for_completed()
        await self.robot.set_head_angle(cozmo.util.Angle(degrees=0)).wait_for_completed()
        await self.robot.play_anim_trigger(cozmo.anim.Triggers.FistBumpSuccess).wait_for_completed()
        await self.robot.play_anim_trigger(cozmo.anim.Triggers.MeetCozmoLookFaceGetOut).wait_for_completed()
        await self.robot.say_text("Ready for the ride", use_cozmo_voice=True, voice_pitch=-1, duration_scalar=1).wait_for_completed()
        img = Image.open("Media/belt.jpg")
        resized_img = img.resize(cozmo.oled_face.dimensions(), Image.BICUBIC)
        screen_data_1 = cozmo.oled_face.convert_image_to_screen_data(resized_img)
        screen_data_2 = cozmo.oled_face.convert_image_to_screen_data(resized_img, invert_image=True)

        while self.robot.is_picked_up is False:
            await self.robot.display_oled_face_image(screen_data_1, duration_ms=200).wait_for_completed()
            await self.robot.display_oled_face_image(screen_data_2, duration_ms=200).wait_for_completed()
            await asyncio.sleep(0)

        self.robot.play_anim_trigger(cozmo.anim.Triggers.DroneModeTurboDrivingStart)

        while self.robot.is_picked_up is True:
            await asyncio.sleep(0)

        if self.mainInstance:
            asyncio.ensure_future(self.mainInstance.ride_started());

        asyncio.ensure_future(self.capture_values())
        await self.spin()
        

if __name__ == '__main__':
    MerryGoRound()