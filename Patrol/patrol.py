import cozmo
import cozmo.event
import asyncio
import time
import threading
import random
from Patrol.Track.track import Track, BldgVertex
from cozmo.util import radians, degrees, distance_mm, speed_mmps
from cozmo.objects import CustomObjectMarkers, CustomObjectTypes
from cozmo.anim import Triggers

FRAME_DURATION = 0.08
FORWARD_SPEED = 50
INNER_SPEED = 10
SEARCH_TURNING_SPEED = 30
TURN_TIME = 1.0
LOADINGDOCK_FORWARD_TIME = 6
MAX_TIME = 100
EPSILON = 0.00001
DISTANCE_TO_PIXEL_SCALE = 4.0
COLOR_TO_BLDG = {
    "Red": "BB",
    "Green": "GB",
    "Blue": "RB",
    "Yellow": "YB",
    "Magenta": "MB"
}
DELIVERY_UNIVERSE = [{"color": "Blue"},{"color": "Red"},{"color": "Green"},{"color": "Yellow"},{"color": "Magenta"}]
MAX_DELIVERY = 5
MAX_ATTENTION = 5
MAX_WAITING_TIME = 15.0
ATTENTION_TRIGGERS = ["CantHandleTallStack", "CozmoSaysBadWord", "CubeMovedUpset", "CubePounceFake", "GoToSleepGetOut"]

class Patrol:
    def __init__(self, remote=None, robot=None):
        self.remote = remote
        self.track = Track()
        
        self.robot = robot

        self.stopped = False
        self.started = False
        
        self.poseTrack = None
        self.initialPose = None
        
        # whether Cozmo is driving along the road, not turn to buildings on sides
        self.driveOnRoad = True
        
        self.waitForOrder = False
        
        self.waitForAnimation = False
        self.offsetPixel = 0.0
        self.acceptOffset = False

        self.deliveryCount = 0
        self.attentionCount = 0

        if remote:
            remote.cozmo.world.add_event_handler(cozmo.objects.EvtObjectAppeared, self.onMarkerSeen)
        
    # entrance of cozmo connection
    async def run(self, coz_conn: cozmo.conn.CozmoConnection):
        robot = await coz_conn.wait_for_robot()

        if not self.remote:
            await self.defineCustomObjects(robot.world)

        robot.world.add_event_handler(cozmo.objects.EvtObjectObserved, self.onMarkerSeen)
        
        await self.start(robot)

    async def start(self, robot: cozmo.robot.Robot):
        if self.started or self.stopped:
            return
        self.started = True
        self.robot = robot

        self.robot.abort_all_actions();
        self.robot.stop_all_motors();

        await robot.set_lift_height(0.8).wait_for_completed()
        await robot.set_head_angle(degrees(30)).wait_for_completed()

        # TODO: this distance is likely to be inaccurate
        await robot.drive_straight(distance_mm(140), speed_mmps(FORWARD_SPEED)).wait_for_completed()
        await robot.turn_in_place(degrees(-90))
        
        # await self.loop(robot)
        await self.loopPath(robot)
        # await self.searchForCustomObject(robot)


    async def searchForCustomObject(self, robot: cozmo.robot.Robot):
        lookAround = robot.start_behavior(cozmo.behavior.BehaviorTypes.LookAroundInPlace)

        obj = None

        try:
            obj = await self.waitForObservedCustomObject(robot, timeout=30)
            print("Found custom obj: %s" % obj)
        except asyncio.TimeoutError:
            print("Didn't find a custom object")
        finally:
            lookAround.stop()

        if obj:
            pass
            #await robot.go_to_object(obj)
    
    async def waitForObservedCustomObject(self, robot: cozmo.robot.Robot, timeout=None):
        filter = cozmo.event.Filter(cozmo.objects.EvtObjectObserved,
                                    obj=lambda obj: isinstance(obj, cozmo.objects.CustomObject))
        evt = await robot.world.wait_for(filter, timeout=timeout)
        return evt.obj

    async def greetToMarker(self, robot: cozmo.robot.Robot):
        # stop
        robot.stop_all_motors()
        # record pose
        pose = robot.pose
        # turn to side
        await robot.turn_in_place(degrees(-90)).wait_for_completed()
        # greet
        await robot.play_anim_trigger(Triggers.NamedFaceInitialGreeting).wait_for_completed()
        # turn back
        await robot.go_to_pose(pose).wait_for_completed()
        # resume moving
        await robot.drive_wheels(FORWARD_SPEED, FORWARD_SPEED)

    async def loop(self, robot: cozmo.robot.Robot):
        if robot.is_on_charger:
            await robot.drive_off_charger_contacts().wait_for_completed()

        self.initialPose = robot.pose
        self.poseTrack = self.track.getPoseTrack(FORWARD_SPEED)
        self.driveOnRoad = True
        self.stopped = False

        await robot.drive_wheels(FORWARD_SPEED, FORWARD_SPEED)
        print(self.poseTrack.edge.end.id)
        
        while not self.stopped:

            # basic update of straight drive
            # picking next edge if the current is finished
            if self.driveOnRoad:
                self.poseTrack.update(FRAME_DURATION, FORWARD_SPEED)

            # back to starting point
            if self.poseTrack.consumeRouteEndSignal():
                self.driveOnRoad = False
                # stop before turn
                robot.stop_all_motors()
                await robot.go_to_pose(self.initialPose).wait_for_completed()
                await robot.drive_wheels(FORWARD_SPEED, FORWARD_SPEED)
                # turning is included in go to pose
                self.poseTrack.consumeEdgeChangeSignal()
                self.driveOnRoad = True
                
                print("fix position at initial pose")
                print(self.poseTrack.edge.end.id)
            # at any other cross or corner
            elif self.poseTrack.consumeEdgeChangeSignal():
                self.driveOnRoad = False
                diff = self.poseTrack.angleDiff
                angleAbs = self.poseTrack.angleAbs
                # make sure the picked next
                if diff < -0.1 or diff > 0.1:
                    # stop before turn
                    robot.stop_all_motors()
                    # make a turn
                    angle = radians(angleAbs + self.initialPose.rotation.angle_z.radians - robot.pose.rotation.angle_z.radians)
                    await robot.turn_in_place(angle).wait_for_completed()
                    print("make a turn")
                    # restart motion
                    await robot.drive_wheels(FORWARD_SPEED, FORWARD_SPEED)
                self.driveOnRoad = True
                
                print(self.poseTrack.edge.end.id)

            # let Cozmo drive straight for a short time before updates
            await asyncio.sleep(FRAME_DURATION)

        robot.stop_all_motors()

    async def loopPath(self, robot: cozmo.robot.Robot):
        if robot.is_on_charger:
            await robot.drive_off_charger_contacts().wait_for_completed()

        self.initialPose = robot.pose
        self.pathPoseTrack = self.track.getPathPoseTrack(FORWARD_SPEED)
        self.driveOnRoad = True
        self.stopped = False

        self.waitForOrder = False
        
        self.waitForAnimation = False
        self.offsetPixel = 0.0

        self.deliveryCount = 0
        self.attentionCount = 0

        print("start drive")
##        await robot.drive_wheels(FORWARD_SPEED, FORWARD_SPEED)
        print(self.pathPoseTrack.distance)
        await robot.drive_straight(distance_mm(self.pathPoseTrack.distance), speed_mmps(FORWARD_SPEED)).wait_for_completed()
        print(self.pathPoseTrack.edge.end.id)
        
        while not self.stopped:

            # basic update of straight drive
            # picking next edge if the current is finished
            if self.driveOnRoad:
##                self.pathPoseTrack.update(FRAME_DURATION, FORWARD_SPEED)
                # finish this path, because drive_straight is used and waited to finish
                self.pathPoseTrack.update(999, FORWARD_SPEED)
                
            # This block will not happen
            # elif self.waitForOrder:
            #     bldgId = self.pathPoseTrack.edge.start.id
            #     nextId = self.pathPoseTrack.edge.end.id
            #     destId = None

            #     deliveryBag = []
            #     if deliveryBag:
            #         # TODO: assign destId
            #         pass

            #     if destId:
            #         self.findPathAndDepart(bldgId, destId, nextId)

            # end of the path
            if self.deliveryCount > MAX_DELIVERY:
                await robot.play_anim_trigger(random.choice(ATTENTION_TRIGGERS)).wait_for_completed()
            elif self.pathPoseTrack.consumeRouteEndSignal():
                self.driveOnRoad = False
                # stop before turn
                robot.stop_all_motors()
                # turning is included in go to pose
                self.pathPoseTrack.consumeEdgeChangeSignal()

                # go to loading area and drop cube
                # lift cube, go back to road
                bldgId = self.pathPoseTrack.edge.start.id
                if bldgId != "GA":
                    await self.deliverItem(robot, self.pathPoseTrack.edge.start, self.pathPoseTrack.path.lastTurnRight)
                else:
                    await self.backInGarage(robot, False)
                    self.stopped = True

                if self.stopped:
                    break
                
                await self.depart(robot)

                print("Move towards: %s" % self.pathPoseTrack.edge.end.id)
                
            # at any other cross or corner
            elif self.pathPoseTrack.consumeEdgeChangeSignal():
                self.driveOnRoad = False
                diff = self.pathPoseTrack.angleDiff
                angleAbs = self.pathPoseTrack.angleAbs
                # make sure the picked next
                if diff < -0.1 or diff > 0.1:
                    # stop before turn
                    robot.stop_all_motors()
                    # make a turn
                    angle = radians(angleAbs + self.initialPose.rotation.angle_z.radians - robot.pose.rotation.angle_z.radians)
                    await robot.turn_in_place(angle).wait_for_completed()
                    print("turn of angle: ", angle.degrees)
                    # restart motion
##                    await robot.drive_wheels(FORWARD_SPEED, FORWARD_SPEED)
                    
                await robot.drive_straight(distance_mm(self.pathPoseTrack.distance), speed_mmps(FORWARD_SPEED)).wait_for_completed()

                self.driveOnRoad = True
                
                print("Move towards: %s" % self.pathPoseTrack.edge.end.id)

            # let Cozmo drive straight for a short time before updates
            await asyncio.sleep(FRAME_DURATION)

        robot.stop_all_motors()

    async def findPathAndDepart(self, startId, endId, nextId, robot: cozmo.robot.Robot):
        path = self.track.getPath(startId, endId, nextId)
        offset = -(self.offsetPixel / DISTANCE_TO_PIXEL_SCALE)
        self.pathPoseTrack.updatePath(path, FORWARD_SPEED, offset)

        # resume motion
##        await robot.drive_wheels(FORWARD_SPEED, FORWARD_SPEED)
        await robot.drive_straight(distance_mm(self.pathPoseTrack.distance), speed_mmps(FORWARD_SPEED)).wait_for_completed()    
        self.driveOnRoad = True
        self.waitForOrder = False

    async def depart(self, robot: cozmo.robot.Robot):
        await robot.drive_straight(distance_mm(self.pathPoseTrack.distance), speed_mmps(FORWARD_SPEED)).wait_for_completed()    
        self.driveOnRoad = True
        self.waitForOrder = False

    def findPath(self, startId, endId, nextId):
        path = self.track.getPath(startId, endId, nextId)
        # offset = -(self.offsetPixel / DISTANCE_TO_PIXEL_SCALE)
        self.pathPoseTrack.updatePath(path, FORWARD_SPEED)

    async def computeDestId(self, bldgId: str, robot: cozmo.robot.Robot):
        deliveryBag = []
        if self.remote:
            # access from remote controller of lights currently on
            deliveryBag = self.remote.lights_on
        else:
            # Mock the colors in bag-----------------
            if bldgId == "PH":
                deliveryBag.append(random.choice(DELIVERY_UNIVERSE))
                pass
            elif bldgId == "RB":
                # deliveryBag.append({"color":"Blue"})
                pass
            # mock finish-------------------------------

        destId = None
        colorName = next((n["color"] for n in deliveryBag if n is not None), None)
        print("Color: %s" % colorName)
        
        if colorName:
            destId = COLOR_TO_BLDG[colorName]
        else:
            if robot.battery_voltage < 3.5:
                destId = "GA"
            elif bldgId == "PH":
                # Start waiting for pizza
                self.waitForOrder = True
            elif bldgId == "GA":
                # Back to home, take rest
                await self.backInGarage(robot, False)
            else:
                destId = "PH"

        if bldgId != "GA" and bldgId != "PH":
            self.deliveryCount = self.deliveryCount + 1

        return destId

    async def deliverItem(self, robot: cozmo.robot.Robot, bldg: BldgVertex, destTurnRight=True):
        pose = robot.pose
        await robot.turn_in_place(degrees(-90 * self.flagToScale(destTurnRight))).wait_for_completed()
##        await robot.drive_wheels(FORWARD_SPEED / 2, FORWARD_SPEED / 2)
##        t = bldg.d / (FORWARD_SPEED / 2)
##        await asyncio.sleep(t)
##        robot.stop_all_motors()
        await robot.drive_straight(distance_mm(bldg.d), speed_mmps(FORWARD_SPEED / 2)).wait_for_completed()
        await robot.set_head_angle(degrees(30)).wait_for_completed()
        self.waitForAnimation = True
        self.acceptOffset = True
        await robot.set_lift_height(0.0 + EPSILON).wait_for_completed()
        await asyncio.sleep(0.1)
        self.acceptOffset = False

        print("Start waiting for animation")
        if self.remote:
            waitingTime = 0.0
            while self.waitForAnimation:
                await asyncio.sleep(0.1)
                if self.stopped:
                    return
                if waitingTime > MAX_WAITING_TIME:
                    return
                waitingTime = waitingTime + 0.1
        else:
            await asyncio.sleep(5)
        print("Finish waiting for animation")

        await robot.set_lift_height(1.0 - EPSILON).wait_for_completed()

        # parameters for path finding
        bldgId = self.pathPoseTrack.edge.start.id
        nextId = self.pathPoseTrack.edge.end.id
        destId = await self.computeDestId(bldgId, robot)
        # find path, update to pathPoseTrack
        self.findPath(bldgId, destId, nextId)
        initTurnLeft = self.pathPoseTrack.path.firstTurnLeft

        # or go to pose
##        await robot.drive_wheels(-FORWARD_SPEED / 2, -FORWARD_SPEED / 2)
##        await asyncio.sleep(t)
##        robot.stop_all_motors()
        await robot.drive_straight(distance_mm(-bldg.d), speed_mmps(FORWARD_SPEED / 2)).wait_for_completed()
        await robot.turn_in_place(degrees(90 * self.flagToScale(initTurnLeft))).wait_for_completed()
        offset = -(self.offsetPixel / DISTANCE_TO_PIXEL_SCALE)
        if abs(offset) < 200:
            self.pathPoseTrack.updateOffset(offset * self.flagToScale(initTurnLeft))
            pass


    async def backInGarage(self, robot: cozmo.robot.Robot, ccrflag: bool):
        await robot.turn_in_place(degrees(90 * self.flagToScale(ccrflag))).wait_for_completed()
        await robot.drive_wheels(-FORWARD_SPEED / 2, -FORWARD_SPEED / 2)
        await asyncio.sleep(2)
        robot.stop_all_motors()

    def disableAuto(self):
        if not self.stopped:
            self.stopped = True
            self.started = False
            self.robot.abort_all_actions()
            self.robot.set_head_angle(cozmo.util.Angle(degrees=30));

    def enableAuto(self):
        if self.stopped:
            self.stopped = False

    def flagToScale(self, flag: bool):
        scale = 1
        if flag == False:
            scale = -1
        return scale

    def onMarkerSeen(self, evt: cozmo.objects.EvtObjectObserved, image_box=None, obj=None, pose=None, **kwargs):
        if self.acceptOffset and isinstance(obj, cozmo.objects.CustomObject):
            self.offsetPixel = image_box.top_left_x + image_box.width * 0.5 - 160
            print("custom marker offset in pixels: ", self.offsetPixel)

    async def onReactiveAnimationFinished(self):
        print("ANIMATION FINISHED");
        self.waitForAnimation = False

    async def defineCustomObjects(self, world):
        cube_obj_1 = await world.define_custom_cube(CustomObjectTypes.CustomType02,
                                                  CustomObjectMarkers.Diamonds2,
                                                  100,
                                                  90, 90, False)
        cube_obj_2 = await world.define_custom_cube(CustomObjectTypes.CustomType03,
                                                             CustomObjectMarkers.Diamonds3,
                                                             100,
                                                             90, 90, True)
        cube_obj_3 = await world.define_custom_cube(CustomObjectTypes.CustomType04,
                                                             CustomObjectMarkers.Diamonds4,
                                                             100,
                                                             90, 90, True)
        cube_obj_4 = await world.define_custom_cube(CustomObjectTypes.CustomType05,
                                                             CustomObjectMarkers.Diamonds5,
                                                             100,
                                                             90, 90, True)

        cube_obj_5 = await world.define_custom_cube(CustomObjectTypes.CustomType06,
                                                             CustomObjectMarkers.Circles2,
                                                             100,
                                                             90, 90, True)
        cube_obj_6 = await world.define_custom_cube(CustomObjectTypes.CustomType07,
                                                             CustomObjectMarkers.Circles3,
                                                             100,
                                                             90, 90, True)
        cube_obj_7 = await world.define_custom_cube(CustomObjectTypes.CustomType08,
                                                             CustomObjectMarkers.Circles4,
                                                             100,
                                                             90, 90, True)
        cube_obj_8 = await world.define_custom_cube(CustomObjectTypes.CustomType09,
                                                             CustomObjectMarkers.Circles5,
                                                             100,
                                                             90, 90, True)

        cube_obj_9 = await world.define_custom_cube(CustomObjectTypes.CustomType10,
                                                             CustomObjectMarkers.Triangles2,
                                                             100,
                                                             90, 90, True)
        cube_obj_10 = await world.define_custom_cube(CustomObjectTypes.CustomType11,
                                                             CustomObjectMarkers.Triangles3,
                                                             100,
                                                             90, 90, True)
        cube_obj_11 = await world.define_custom_cube(CustomObjectTypes.CustomType12,
                                                             CustomObjectMarkers.Triangles4,
                                                             100,
                                                             90, 90, True)
        cube_obj_12 = await world.define_custom_cube(CustomObjectTypes.CustomType13,
                                                             CustomObjectMarkers.Triangles5,
                                                             100,
                                                             90, 90, True)

        cube_obj_13 = await world.define_custom_cube(CustomObjectTypes.CustomType14,
                                                             CustomObjectMarkers.Hexagons2,
                                                             100,
                                                             90, 90, True)
        cube_obj_14 = await world.define_custom_cube(CustomObjectTypes.CustomType15,
                                                             CustomObjectMarkers.Hexagons3,
                                                             100,
                                                             90, 90, True)
        cube_obj_15 = await world.define_custom_cube(CustomObjectTypes.CustomType16,
                                                             CustomObjectMarkers.Hexagons4,
                                                             100,
                                                             90, 90, True)
        cube_obj_16 = await world.define_custom_cube(CustomObjectTypes.CustomType17,
                                                             CustomObjectMarkers.Hexagons5,
                                                             100,
                                                             90, 90, True)

def main():
    p = Patrol()
    cozmo.setup_basic_logging()
    cozmo.connect_with_tkviewer(p.run)

if __name__ == "__main__":
    main()
    
