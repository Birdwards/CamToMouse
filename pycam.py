#todo: hotkey for toggling tracking on/off
#todo: why is click working correctly in separate thread? is it just because canvas cleared?
#     or if keeping click in separate thread, maybe calculate click window in that thread instead of waiting for next iteration of loop for should_click to be true 
#todo: does choice of color transform affect accuracy of pose detection?
#todo: resizable mouse range
#todo: change to pynput so we can also monitor keyboard (eg for hotkey) and mouse (eg for clicked flag)

#apparently fixes webcam taking forever to load
import os
os.environ["OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS"] = "0"

import numpy as np
import cv2 as cv
import mediapipe as mp
import time
import math
import pyautogui
from mediapipe.tasks.python.vision import drawing_utils
from mediapipe.tasks.python.vision import drawing_styles
from mediapipe.tasks.python import vision

#from hidpi_tk import DPIAwareTk
import tkinter as tk
import threading
import PIL.Image
import PIL.ImageTk

recent_timestamp = None
recent_result = None
recent_image = None
recent_position = None
cap = None
recent_positions = dict()
linger_start = None

fps = 144.0 #todo: selectable fps
frame_ms = int(1000.0/fps+0.5)
average_window = 500.0
click_window = 1000.0
indicator_window = 500.0
indicator_radius = 25.0
indicator_width = 4.0
linger_radius = 15
click_cooldown = 1000
start_cooldown = 3000
click_ready = int(time.time() * 1000) + start_cooldown
should_click = False
clicked = False
queued_pos = None

screen_size = pyautogui.size()
screen_width = screen_size[0]
screen_height = screen_size[1]

BaseOptions = mp.tasks.BaseOptions
PoseLandmarker = mp.tasks.vision.PoseLandmarker
PoseLandmarkerOptions = mp.tasks.vision.PoseLandmarkerOptions
PoseLandmarkerResult = mp.tasks.vision.PoseLandmarkerResult
VisionRunningMode = mp.tasks.vision.RunningMode

#root=DPIAwareTk()
root=tk.Tk()
#root.geometry('2560x1440') #todo: get resolution from pyautogui
root.overrideredirect(True) #remove title bar
root.attributes("-transparentcolor","red")
root.config(bg="red")
#canvas = tk.Canvas(root, width=2560, height=1440, bg='red', highlightthickness=0)
canvas = tk.Canvas(root, width=indicator_radius*2, height=indicator_radius*2, bg='red', highlightthickness=0)
canvas.pack()
#canvas.pack(fill=tk.BOTH, expand=True)
#test_rect = canvas.create_rectangle(0,0,50,50,fill='blue')
inner_ring = canvas.create_oval(0,0,0,0, outline='white', width=indicator_width)
outer_ring = canvas.create_oval(0,0,0,0, outline='black', width=indicator_width)
root.wm_attributes("-topmost", 1)


nose = None
def draw_cursor(): #todo: can we get rate of this below 1 per 100 ms? choice of model doesn't seem to make a difference
  print("draw_cursor: " + str(int(time.time() * 1000)))
  #cur_pos = pyautogui.position()
  #root.geometry('100x100+'+str(cur_pos[0]-50)+'+'+str(cur_pos[1]+50))
  canvas.coords(outer_ring, -indicator_width, -indicator_width, -indicator_width, -indicator_width)
  canvas.coords(inner_ring, -indicator_width, -indicator_width, -indicator_width, -indicator_width)

  
  global queued_pos
  if queued_pos:
    pyautogui.moveTo(queued_pos[0], queued_pos[1]) #move to pos a frame late so indicator is in sync
  
  if nose:
    mouse_x = nose.x * screen_width
    mouse_y = nose.y * screen_height

    global recent_timestamp
    global recent_position
    global recent_positions
    if not recent_timestamp in recent_positions:
      recent_position = [mouse_x, mouse_y]
      recent_positions.update({recent_timestamp: recent_position})

    global average_window
    now = int(time.time() * 1000)
    last_time = now
    start_popping = False
    average = [0,0]
    for timestamp in sorted(recent_positions.keys(), reverse=True):
      if start_popping:
        recent_positions.pop(timestamp)
      else:
        pct = (last_time-max(timestamp, now - average_window))/average_window
        average[0] += recent_positions.get(timestamp)[0]*pct
        average[1] += recent_positions.get(timestamp)[1]*pct
        
        last_time = timestamp
        if now - timestamp > average_window:
          start_popping = True

    global click_window
    global indicator_window
    global click_ready
    global linger_start
    queued_pos = average
    root.geometry(
        '+'+str(int(average[0]-25))+
        '+'+str(int(average[1]-25))
        )
    if now > click_ready and math.hypot(average[0]-recent_position[0], average[1]-recent_position[1]) < linger_radius:
      if linger_start == None:
        linger_start = now# - average_window
        #print("linger start")
      else:
        linger_time = now - linger_start
        if linger_time > click_window:
          global should_click
          canvas.pack_forget()
          should_click = True
          #pyautogui.click()
          click_ready = now + click_cooldown
          print("click") #todo: cooldown after click
        elif linger_time > click_window - indicator_window:
          r = (click_window-linger_time)/indicator_window * (indicator_radius - indicator_width*1.5)
          ro = r + indicator_width
          canvas.coords(outer_ring, indicator_radius-ro, indicator_radius-ro, indicator_radius+ro, indicator_radius+ro)
          canvas.coords(inner_ring, indicator_radius-r, indicator_radius-r, indicator_radius+r, indicator_radius+r)
          #print("lingering")
    else:
      linger_start = None
      #print("moving")
  canvas.after(frame_ms, draw_cursor)

draw_cursor()

window = tk.Toplevel()
cam_canvas = tk.Canvas(window, width=640, height=480, bg='gray', highlightthickness=0)
cam_canvas.pack()
load_img = PIL.ImageTk.PhotoImage(PIL.Image.open("load.png"))
image_for_canvas = np.empty(0)
image_tk = None
camview = cam_canvas.create_image(320,240, image=load_img)#todo: path relative to run directory

def draw_webcam():
  global cam_canvas
  global camview
  global image_tk
  if image_for_canvas.any():
    image_tk = PIL.ImageTk.PhotoImage(PIL.Image.fromarray(image_for_canvas))
    cam_canvas.itemconfig(camview, image=image_tk)
  cam_canvas.after(frame_ms, draw_webcam)
  
draw_webcam()

should_release = False
should_close = False
def close_app():
  global should_release
  global should_close
  should_release = True
  while not should_close:
    time.sleep(0.01)
  root.quit()

button = tk.Button(window,text="Close",command=close_app)
button.pack()

'''def lerp(a, b, pct):
  return (1-pct)*a + pct*b'''
  
def draw_landmarks_on_image(rgb_image, detection_result):
  pose_landmarks_list = detection_result.pose_landmarks
  annotated_image = np.copy(rgb_image)

  global nose
  if len(pose_landmarks_list) > 0:
    nose = pose_landmarks_list[0][0] #todo: if multiple poses detected, is there a way to tell which one is same as one from previous frame?
  else:
    nose = None
  
  pose_landmark_style = drawing_styles.get_default_pose_landmarks_style()
  pose_connection_style = drawing_utils.DrawingSpec(color=(0, 255, 0), thickness=2)

  for pose_landmarks in pose_landmarks_list:
    drawing_utils.draw_landmarks(
        image=annotated_image,
        landmark_list=pose_landmarks,
        connections=vision.PoseLandmarksConnections.POSE_LANDMARKS,
        landmark_drawing_spec=pose_landmark_style,
        connection_drawing_spec=pose_connection_style)

  return annotated_image

# Create a pose landmarker instance with the live stream mode:
def print_result(result: PoseLandmarkerResult, output_image: mp.Image, timestamp_ms: int):
    global recent_timestamp
    if recent_timestamp and timestamp_ms <= recent_timestamp:
        return
    
    global recent_result
    global recent_image

    recent_timestamp = timestamp_ms
    recent_result = result
    recent_image = output_image

options = PoseLandmarkerOptions(
    base_options=BaseOptions(model_asset_path='pose_landmarker_full.task'), #todo: make path relative to .py/.exe rather than relative to running directory
    running_mode=VisionRunningMode.LIVE_STREAM,
    result_callback=print_result)

def cam_thread():
  with PoseLandmarker.create_from_options(options) as landmarker:
    # The landmarker is initialized. Use it here.
      global cap
      cap = cv.VideoCapture(1) #todo: selectable camera
      if not cap.isOpened():
          print("Cannot open camera")
          exit()
      #while True:
      while cap.isOpened():
          global should_release
          if should_release:
              break
          # Capture frame-by-frame
          print("before capture: " + str(int(time.time() * 1000)))
          ret, frame = cap.read()
          print("after capture: " + str(int(time.time() * 1000)))

          global should_click
          global clicked
          if clicked:
            canvas.pack()
            clicked = False
          if should_click:
            pyautogui.click()
            should_click = False
            clicked = True
       
          # if frame is read correctly ret is True
          if not ret:
              print("Can't receive frame (stream end?). Exiting ...")
              break
          # Our operations on the frame come here
          #rgb_frame = cv.cvtColor(frame, cv.COLOR_BGR2RGB)
          flipped_frame = cv.flip(frame, 1)
          mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=flipped_frame)
          detection_result = landmarker.detect_async(mp_image, int(time.time() * 1000))
          # Display the resulting frame
          if recent_result != None:
              global image_for_canvas
              annotated_image = draw_landmarks_on_image(recent_image.numpy_view(), recent_result)
              #todo: aspect ratio-aware resize
              image_for_canvas = cv.cvtColor(cv.resize(annotated_image, (640, 480)), cv.COLOR_BGR2RGB) #todo: move earlier in pipeline for performance (but you'll have to also transform landmark coords if you do)

              #cv.imshow('frame2', annotated_image)
  # When everything done, release the capture
  global should_close
  cap.release()
  cv.destroyAllWindows()
  should_close = True

thread = threading.Thread(target=cam_thread, daemon=True) #todo: make non-daemonic; release cap properly on tkinter exit
thread.start()

root.mainloop()
