import tkinter as tk
from PIL import Image, ImageDraw, ImageTk
import numpy as np
import threading

root = tk.Tk()
W, H = 500, 500
canvas = tk.Canvas(root, width=W, height=H, bg="white")
canvas.pack()

img = Image.new("RGB", (W, H), "white")
draw = ImageDraw.Draw(img)
photo = ImageTk.PhotoImage(img)
canvas_img = canvas.create_image(0, 0, anchor="nw", image=photo)

px, py = 250, 250
direction = "stop"
speed = 4
last_px, last_py = px, py
frame = 0
filling = False

head = canvas.create_rectangle(px, py, px+15, py+15, fill="blue", outline="white", width=2)

def try_fill():
    global filling
    filling = True
    temp = img.copy()
    for corner in [(0,0), (W-1,0), (0,H-1), (W-1,H-1)]:
        ImageDraw.floodfill(temp, corner, (255,0,0), thresh=10)
    arr = np.array(temp)
    orig = np.array(img)
    outside = (arr[:,:,0] == 255) & (arr[:,:,1] == 0)
    blue = (orig[:,:,2] > 200) & (orig[:,:,0] < 50)
    orig[~outside & ~blue] = [0, 0, 255]
    img.paste(Image.fromarray(orig))
    filling = False

def redraw():
    global photo
    photo = ImageTk.PhotoImage(img)
    canvas.itemconfig(canvas_img, image=photo)
    canvas.tag_raise(head)

def game_loop():
    global px, py, last_px, last_py, frame

    if direction == "left":  px -= speed
    if direction == "right": px += speed
    if direction == "up":    py -= speed
    if direction == "down":  py += speed

    px = max(0, min(485, px))
    py = max(0, min(485, py))

    if direction != "stop":
        draw.line([(last_px+7, last_py+7), (px+7, py+7)], fill="blue", width=15)
        draw.rectangle([(px, py), (px+14, py+14)], fill="blue")

        # run fill in background every 10 frames
        if frame % 10 == 0 and not filling:
            threading.Thread(target=try_fill, daemon=True).start()

    last_px, last_py = px, py
    canvas.coords(head, px, py, px+15, py+15)

    frame += 1
    if frame % 2 == 0:
        redraw()

    root.after(8, game_loop)

root.bind("<Left>",  lambda e: globals().update(direction="left"))
root.bind("<Right>", lambda e: globals().update(direction="right"))
root.bind("<Up>",    lambda e: globals().update(direction="up"))
root.bind("<Down>",  lambda e: globals().update(direction="down"))

game_loop()
root.mainloop()