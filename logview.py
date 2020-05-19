from base64 import b64decode
import gzip
import json

import tkinter as tk
from tkinter.filedialog import askopenfilename
import pygubu
from PIL import Image, ImageTk


def bits(number):
    yield 0 if number & 0b00000001 != 0 else 1
    yield 0 if number & 0b00000010 != 0 else 1
    yield 0 if number & 0b00000100 != 0 else 1
    yield 0 if number & 0b00001000 != 0 else 1
    yield 0 if number & 0b00010000 != 0 else 1
    yield 0 if number & 0b00100000 != 0 else 1
    yield 0 if number & 0b01000000 != 0 else 1
    yield 0 if number & 0b10000000 != 0 else 1

BLANK_IMAGE = Image.new("RGBA", (230, 80), (0xff, 0xff, 0xff, 0xff))

def decode_image(imageStr):
    bytes = b64decode(imageStr)
    width = 230
    height = 80
    im = Image.new("RGBA", (width, height), (0xff, 0xff, 0xff, 0xff))

    x = 0
    y = 0
    for byte in bytes:
        for bit in bits(byte):
            im.putpixel((x, y), (0xff, 0xff, 0xff, 0xff) if bit else (0x00, 0x00, 0x00, 0xff))
            x += 1
            if x >= width:
                y += 1
                x = 0
    return im

class LogViewApp(pygubu.TkApplication):
    def __init__(self):
        self.builder = pygubu.Builder()
        self.builder.add_from_file("logview.ui")
        self.mainwindow = self.builder.get_object("mainwindow")
        self.builder.connect_callbacks(self)
        self.builder.get_object("message_list").bind("<<TreeviewSelect>>", self.tree_select)
        self.json_data = []
        self.tree_data = []

    def run(self):
        self.mainwindow.mainloop()

    def on_filepicker_button(self):
        self.filename = askopenfilename(filetypes=(("log files", "*.json"),("log files", "*.json.gz"),("all files","*.*")))
        self.builder.get_object("filename").config(text=self.filename)
        if len(self.filename) > 0:
            self.load_log(self.filename)

    def set_message_text(self, string):
        text = self.builder.get_object("message_text")
        text.config(state=tk.NORMAL)
        text.delete(1.0, tk.END)
        text.insert(tk.END, string)
        text.config(state=tk.DISABLED)

    def set_message_image(self, image):
        label = self.builder.get_object("message_image")
        render = ImageTk.PhotoImage(image)
        label.config(image=render)
        label.image = render

    def update_tree(self):
        json_data = self.json_data
        message_list = self.builder.get_object("message_list")

        if len(message_list.selection()) > 0:
            message_list.selection_remove(message_list.selection()[0])

        message_list.delete(*message_list.get_children())
        message_list["columns"] = ("user")
        message_list.heading("user", text="User")

        actions = []
        if self.builder.get_variable("typevar_connect").get():
            actions.append("connect")
        if self.builder.get_variable("typevar_status").get():
            actions.append("status")
        if self.builder.get_variable("typevar_username").get():
            actions.append("username")
        if self.builder.get_variable("typevar_join").get():
            actions.append("join")
        if self.builder.get_variable("typevar_disconnect").get():
            actions.append("disconnect")
        if self.builder.get_variable("typevar_message").get():
            actions.append("message")

        self.tree_data = []
        index = 0
        for item in json_data:
            if "action" in item.keys():
                if item["action"] in actions:
                    self.tree_data.append(item)
                    index += 1
                    message_list.insert("", "end", id=index, values=( self.parse_item(item)[0] ))

    def parse_item(self, item):
        action = item["action"]
        if action == "connect":
            return ("SERVER/connect", str(item))
        elif action == "status":
            return ("SERVER/status", str(item))
        elif action == "username":
            return ("SERVER/username", str(item))
        elif action == "join":
            return ("SERVER/join", str(item))
        elif action == "disconnect":
            return ("SERVER/disconnect", str(item))
        elif action == "message":
            try:
                user = item["message"]["user"]
            except:
                user = "<NO USER>"
            return (
                user,
                "<{}>: {}".format(user, item["message"]["data"]),
                item["message"]["image"] if len(item["message"]["image"]) > 0 else None
            )

    def tree_select(self, event):
        message_list = self.builder.get_object("message_list")

        if len(message_list.selection()) == 0:
            return

        id = message_list.selection()[0]
        item = message_list.item(id)
        index = int(id) - 1
        message = self.tree_data[index]

        item = self.parse_item(message)

        self.set_message_text(item[1])
        if len(item) < 3 or not item[2]:
            self.set_message_image(BLANK_IMAGE)
        else:
            self.set_message_image(decode_image(item[2]))

    def load_log(self, filename):
        json_data = []
        if filename.endswith(".json.gz"):
            with gzip.open(filename, "rb") as f:
                file_str = f.read().decode()
                split = file_str.split("\n")
                for line in split:
                    try:
                        json_data.append(json.loads(line))
                    except:
                        pass
        else:
            with open(filename, "r") as f:
                for line in f.readlines():
                    json_data.append(json.loads(line))
        self.json_data = json_data
        self.update_tree()

if __name__ == "__main__" :
    root = tk.Tk()
    root.title("LogView")
    app = LogViewApp()
    app.run()
