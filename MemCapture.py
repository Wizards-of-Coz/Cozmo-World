import cozmo
import asyncio
from Common.woc import WOC
from InstagramAPI import InstagramAPI
from Common.colors import Colors
import speech_recognition as sr
import _thread
import time
import os
import sys

from cv2 import VideoWriter, VideoWriter_fourcc, imread, resize

try:
    import numpy as np
except ImportError:
    print("Cannot import numpy: Do `pip3 install --user numpy` to install")

try:
    from PIL import Image
    from PIL import ImageFilter
except ImportError:
    print("Cannot import from PIL: Do `pip3 install --user Pillow` to install")


class MemCapture(WOC):
    FILTER_FOLDER_NAME = "Filters"              # Folder name where all the 14 filters generated are saved
    VIDEO_IMAGES_FOLDER_NAME = "VideoImages"    # Folder name where the images are saved
    OUTPUT_IMAGE_NAME = "thumbnail.jpg"         # Thumbnail Image name
    INSTAGRAM_USER_NAME = "wizardsofcoz"        # Enter your Instagram Username here
    INSTAGRAM_PASSWORD = ""                     # Enter your Instagram Password here or create a file "instagram.txt" and write the password there in the first line
    OUTPUT_VIDEO_NAME = "video.avi"             # Video name
    INSTAGRAM_FILE_NAME = "instagram.txt"       # Text file to store your password

    def __init__(self, robot=None, instance=None):
        WOC.__init__(self)

        if os.path.exists(self.OUTPUT_VIDEO_NAME):
            os.remove(self.OUTPUT_VIDEO_NAME)

        if self.INSTAGRAM_PASSWORD == "":
            with open(self.INSTAGRAM_FILE_NAME) as f:
                self.INSTAGRAM_PASSWORD = f.readlines()[0];

        self.insta = InstagramAPI(self.INSTAGRAM_USER_NAME, self.INSTAGRAM_PASSWORD)
        self.insta.login()  # login

        self.minstance = instance
        self.coz = robot

        if self.coz is None:
            cozmo.setup_basic_logging()
            cozmo.connect(self.run)

    async def run(self, coz_conn):
        asyncio.set_event_loop(coz_conn._loop)
        self.coz = await coz_conn.wait_for_robot()

        await self.start_program()

        while not self.exit_flag:
            await asyncio.sleep(0)
        self.coz.abort_all_actions()

    async def calc_pixel_threshold(self, image: Image):
        grayscale_image = image.convert('L')
        mean_value = np.mean(grayscale_image.getdata())
        return mean_value

    async def start_program(self):
        self.coz.camera.color_image_enabled = True
        self.coz.camera.image_stream_enabled = True

        self.latest_Image = None;

        self.face_dimensions = cozmo.oled_face.SCREEN_WIDTH, cozmo.oled_face.SCREEN_HALF_HEIGHT
        self.image_taken = False;

        self.handler1 = self.coz.world.add_event_handler(cozmo.camera.EvtNewRawCameraImage, self.on_raw_cam_image)

        self.do_final_anim = False;

        await self.clickPicture();

        while True:
            if self.do_final_anim:
                if self.minstance is not None:
                    await self.minstance.memory_captured();
                else:
                    self.exit_flag = True
                break;
            else:
                await asyncio.sleep(0.1);

    async def on_raw_cam_image(self, event, *, image, **kw):
        self.latest_Image = image;

    async def clickPicture(self):
        self.image_taken = True;

        if not os.path.exists(self.VIDEO_IMAGES_FOLDER_NAME):
            os.makedirs(self.VIDEO_IMAGES_FOLDER_NAME)
        self.max_count = 60;                                                 # Number of images to make the video
        cur_count = 0;
        while self.latest_Image is None:
            print("is none");
            await asyncio.sleep(0.1);

        while cur_count < self.max_count:
            self.latest_Image.save(self.VIDEO_IMAGES_FOLDER_NAME+"/image" + str(cur_count) + ".jpg");
            await asyncio.sleep(0.1);
            cur_count += 1;

        image = self.latest_Image
        img = image.convert('L')
        img.save(self.OUTPUT_IMAGE_NAME)

        self.coz.world.remove_event_handler(cozmo.camera.EvtNewRawCameraImage, self.handler1);

        # comment this to not upload a video
        await self.make_video_and_upload();

        self.do_final_anim = True;

    async def make_video_and_upload(self):
        outvid = self.OUTPUT_VIDEO_NAME
        fps = 24;
        size = (320, 240);
        is_color = 1;

        fourcc = VideoWriter_fourcc(*'XVID')
        vid = None
        images = []
        for i in range(0, self.max_count):
            images.append(self.VIDEO_IMAGES_FOLDER_NAME+"/image" + str(i) + ".jpg")

        for image in images:
            if not os.path.exists(image):
                raise FileNotFoundError(image)
            img = imread(image)
            if vid is None:
                if size is None:
                    size = img.shape[1], img.shape[0]
                vid = VideoWriter(outvid, fourcc, float(fps), size, is_color)
            if size[0] != img.shape[1] and size[1] != img.shape[0]:
                img = resize(img, size)
            vid.write(img)
        vid.release()

        self.insta.uploadVideo("video.avi", thumbnail=self.OUTPUT_IMAGE_NAME, caption="#memorieswithcozmo");


if __name__ == '__main__':
    MemCapture()
