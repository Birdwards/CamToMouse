import pyautogui
import keyboard
import time

was_pressed = False

while True:
    is_pressed = keyboard.is_pressed('q')
    if is_pressed and not was_pressed:
        pyautogui.click()
        print("click")
    was_pressed = is_pressed
    time.sleep(0.01)
