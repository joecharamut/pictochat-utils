import json
import re
import os

import tkinter as tk
from tkinter import filedialog as tkfd
from tkinter import messagebox as tkmb
from tkinter import simpledialog as tksd

import pygubu
from PIL import Image, ImageTk, ImageOps, ImageChops


class LayoutObject():
    def __init__(self, id):
        self.x = 0
        self.y = 0
        self.w = 0
        self.h = 0
        self.variant = "default"
        self.enabled = True
        self.id = id
        self.canvas_id = None
        self.tree_id = None
        self.selected = False
        self.drag_offset = (0, 0)

    def draw(self, canvas):
        pass

    def set_props(self, components):
        for name, object in components.items():
            if name == "id":
                object.state(["!disabled"])
                object.delete(0, tk.END)
                object.insert(0, self.id)
            elif name == "variant":
                object.state(["!disabled"])
                object.delete(0, tk.END)
                object.insert(0, self.variant)
            elif name == "enabled":
                object.state(["!disabled"])
                if self.enabled:
                    object.state(["selected"])
                else:
                    object.state(["!selected"])
            elif name == "x":
                object.state(["!disabled"])
                object.set(self.x)
            elif name == "y":
                object.state(["!disabled"])
                object.set(self.y)

class ObjectImage(LayoutObject):
    BLANK_IMAGE = Image.new("RGBA", (32, 32), (0xaa, 0xaa, 0xaa, 0xff))

    def __init__(self, id, image):
        super().__init__(id)
        self.image_path = ""
        self.image_real_path = ""
        self.set_image(image)

    def set_image(self, image):
        self.image = image
        self.select_image = ImageChops.blend(image, Image.new('RGBA', image.size, (0x00, 0x00, 0xff, 0xff)), 0x44/0xff)

        self.c_image = ImageTk.PhotoImage(self.image)
        self.c_select_image = ImageTk.PhotoImage(self.select_image)

        self.w = image.width
        self.h = image.height

    def draw(self, canvas):
        # print(f"draw({self.id}, {self.x}, {self.y}, {self.w}, {self.h})")
        self.canvas_id = canvas.create_image(self.x+1, self.y+1, image=self.c_image if not self.selected else self.c_select_image, anchor=tk.NW)

    def set_props(self, components):
        super().set_props(components)
        for name, object in components.items():
            if name == "image":
                object.state(["!disabled"])
            elif name == "image_name":
                object.state(["!disabled"])
                object.delete(0, tk.END)
                object.insert(0, self.image_path)
                object.state(["disabled"])

    def refresh_image(self):
        self.set_image(Image.open(self.image_real_path))

class ObjectButton(ObjectImage):
    def __init__(self, id, image, tint):
        super().__init__(id, image)
        self.tint = tint

    def set_props(self, components):
        super().set_props(components)
        for name, object in components.items():
            if name == "tint":
                object.state(["!disabled"])
                object.delete(0, tk.END)
                object.insert(0, self.tint)
            elif name == "tint_preview":
                object.config(bg=self.tint)

class LayoutApp():
    def __init__(self):
        self.builder = pygubu.Builder()
        self.builder.add_from_file("layout.ui")

        self.mainwindow = self.builder.get_object("toplevel")
        self.menu = self.builder.get_object("menu")
        self.mainwindow["menu"] = self.menu

        self.prop_dialog = self.builder.get_object("properties_dialog")
        self.prop_dialog.parent = self.mainwindow

        self.builder.connect_callbacks(self)

        self.mainwindow.bind("<Delete>", self.edit_delete_callback)
        self.mainwindow.bind("<Control-s>", self.save_callback)
        self.mainwindow.protocol("WM_DELETE_WINDOW", self.quit_callback)

        self.object_tree = self.builder.get_object("object_tree")
        self.canvas = self.builder.get_object("layout_canvas")

        self.objects = []
        self.width = 256
        self.height = 384

        self.properties = {
            "id": self.builder.get_object("prop_id_input"),
            "variant": self.builder.get_object("prop_variant_input"),
            "x": self.builder.get_object("prop_x_input"),
            "y": self.builder.get_object("prop_y_input"),
            "enabled": self.builder.get_object("prop_enabled_input"),
            "image": self.builder.get_object("prop_image_select"),
            "image_name": self.builder.get_object("prop_image_input"),
            "tint": self.builder.get_object("prop_tint_input"),
            "tint_preview": self.builder.get_object("prop_tint_preview"),
        }

        self.sel_buttons = [
            self.builder.get_object("pos_up"),
            self.builder.get_object("pos_down"),
            self.builder.get_object("pos_tofront"),
            self.builder.get_object("pos_toback"),
        ]

        self.selected_object = None

        self.the_file = None

        self.img_root = None
        self.load_conf()

        self.refresh_canvas()
        self.refresh_props()

    def run(self):
        if not self.img_root:
            self.mainwindow.after(10, self.menu_properties)
        self.mainwindow.mainloop()

    def save_conf(self):
        with open("layout.conf", "w") as f:
            json_o = {
                "img_root": self.img_root,
            }
            f.write(json.dumps(json_o))

    def load_conf(self):
        if os.path.exists("layout.conf"):
            with open("layout.conf", "r") as f:
                json_f = json.loads(f.read())
            self.img_root = json_f["img_root"]

    def serialize(self, objects):
        json_out = {}

        json_out["objects"] = []
        json_out["w"] = self.width
        json_out["h"] = self.height

        for obj in objects:
            json_obj = {}

            json_obj["type"] = type(obj).__name__
            json_obj["id"] = obj.id
            json_obj["variant"] = obj.variant
            json_obj["enabled"] = obj.enabled
            json_obj["x"] = obj.x
            json_obj["y"] = obj.y

            if type(obj) == ObjectImage:
                json_obj["props"] = {
                    "image": obj.image_path
                }
            elif type(obj) == ObjectButton:
                json_obj["props"] = {
                    "image": obj.image_path,
                    "tint": obj.tint
                }

            json_out["objects"].append(json_obj)

        return json.dumps(json_out)

    def deserialize(self, string):
        json_in = json.loads(string)
        resolved_out = []

        for json_obj in json_in["objects"]:
            type =  json_obj["type"]
            obj = None

            if type == "ObjectImage":
                path = self.img_root + "/" + json_obj["props"]["image"]
                img = Image.open(path) if json_obj["props"]["image"] else ObjectImage.BLANK_IMAGE
                obj = ObjectImage(json_obj["id"], img)
                obj.image_path = json_obj["props"]["image"]
                obj.image_real_path = path
            elif type == "ObjectButton":
                path = self.img_root + "/" + json_obj["props"]["image"]
                img = Image.open(path) if json_obj["props"]["image"] else ObjectImage.BLANK_IMAGE
                obj = ObjectButton(json_obj["id"], img, json_obj["props"]["tint"])
                obj.image_path = json_obj["props"]["image"]
                obj.image_real_path = path

            obj.variant = json_obj["variant"]
            obj.enabled = json_obj["enabled"]
            obj.x = json_obj["x"]
            obj.y = json_obj["y"]
            resolved_out.append(obj)

        self.width = json_in["w"]
        self.height = json_in["h"]

        return resolved_out

    def validate_number(self, newtext):
        return re.match(r"^[0-9]*$", newtext) != None

    def open_callback(self):
        select = tkfd.askopenfilename(
            filetypes=(("layout files", "*.layout"),("all files","*.*"))
        )
        if select:
            self.the_file = select
            with open(self.the_file, "r") as f:
                self.objects = self.deserialize(f.read())
            self.selected_object = None
            self.refresh_tree()
            self.refresh_canvas()
            self.refresh_props()

    def save_callback(self, event=None):
        if not self.the_file:
            return self.saveas_callback()
        with open(self.the_file, "w") as f:
            f.write(self.serialize(self.objects))
        return True

    def saveas_callback(self):
        select = tkfd.asksaveasfilename(
            filetypes=(("layout files", "*.layout"),("all files","*.*")),
            defaultextension=".layout",
            initialdir=self.img_root
        )
        if select:
            self.the_file = select
            return self.save_callback()
        return False

    def quit_callback(self):
        choice = tkmb.askyesnocancel("Quit", "Do you want to save your changes?")
        if choice == True:
            if self.save_callback():
                self.mainwindow.quit()
        elif choice == False:
            self.mainwindow.quit()
        else:
            pass # choice == None

    def new_image_callback(self):
        new_id = 0
        for object in self.objects:
            if isinstance(object, ObjectImage):
                new_id += 1

        new = ObjectImage(f"image_{new_id}", ObjectImage.BLANK_IMAGE)
        self.objects.append(new)
        self.selected_object = new
        self.refresh_tree()
        self.refresh_canvas()
        self.refresh_props()

    def new_button_callback(self):
        new_id = 0
        for object in self.objects:
            if isinstance(object, ObjectButton):
                new_id += 1

        new = ObjectButton(f"button_{new_id}", ObjectImage.BLANK_IMAGE, "#ffffff")
        self.objects.append(new)
        self.selected_object = new
        self.refresh_tree()
        self.refresh_canvas()
        self.refresh_props()

    def new_text_callback(self):
        ...

    def menu_properties(self):
        if self.img_root:
            object = self.builder.get_object("props_basedir_path")
            object.state(["!readonly"])
            object.delete(0, tk.END)
            object.insert(0, self.img_root)
            object.state(["readonly"])

        self.builder.get_variable("props_width_var").set(self.width)
        self.builder.get_variable("props_height_var").set(self.height)

        self.prop_dialog.show()

    def props_close_callback(self):
        self.prop_dialog.close()

    def props_select_base_dir_callback(self):
        select = tkfd.askdirectory(mustexist=True, parent=self.prop_dialog.toplevel, initialdir=self.img_root)
        if select:
            self.img_root = select
            self.save_conf()
            object = self.builder.get_object("props_basedir_path")
            object.state(["!readonly"])
            object.delete(0, tk.END)
            object.insert(0, select)
            object.state(["readonly"])

    def props_width_callback(self, event):
        self.width = self.builder.get_variable("props_width_var").get()
        self.canvas.configure(width=self.width, height=self.height)

    def props_height_callback(self, event):
        self.height = self.builder.get_variable("props_height_var").get()
        self.canvas.configure(width=self.width, height=self.height)

    def get_selected_index(self):
        for i, object in enumerate(self.objects):
            if object == self.selected_object:
                return i
        return None

    def pos_up_callback(self):
        idx = self.get_selected_index()
        if idx == 0:
            return

        tmp = self.objects[idx - 1]
        self.objects[idx - 1] = self.objects[idx]
        self.objects[idx] = tmp

        self.refresh_tree()
        self.refresh_canvas()
        self.refresh_props()

    def pos_down_callback(self):
        idx = self.get_selected_index()
        if idx == len(self.objects) - 1:
            return

        tmp = self.objects[idx + 1]
        self.objects[idx + 1] = self.objects[idx]
        self.objects[idx] = tmp

        self.refresh_tree()
        self.refresh_canvas()
        self.refresh_props()

    def pos_tofront_callback(self):
        idx = self.get_selected_index()
        top = len(self.objects) - 1
        if idx == top:
            return

        tmp = self.objects[top]
        self.objects[top] = self.objects[idx]
        self.objects[idx] = tmp

        self.refresh_tree()
        self.refresh_canvas()
        self.refresh_props()

    def pos_toback_callback(self):
        idx = self.get_selected_index()
        if idx == 0:
            return

        tmp = self.objects[0]
        self.objects[0] = self.objects[idx]
        self.objects[idx] = tmp

        self.refresh_tree()
        self.refresh_canvas()
        self.refresh_props()

    def edit_delete_callback(self, event=None):
        if not self.selected_object:
            return
        idx = self.get_selected_index()

        resp = tkmb.askokcancel(f"Delete?", f"Delete {self.selected_object.id}?")

        if resp:
            del self.objects[idx]
            self.selected_object = None

            self.refresh_tree()
            self.refresh_canvas()
            self.refresh_props()

    def canvas_click(self, event):
        items = self.canvas.find_overlapping(event.x, event.y, event.x, event.y)
        if len(items) > 0:
            id = items[-1]
            for object in self.objects:
                if object.canvas_id == id:
                    break
            self.selected_object = object
            object.drag_offset = (event.x - object.x, event.y - object.y)
            self.refresh_tree()
        else:
            self.selected_object = None
            self.refresh_tree()
            self.refresh_canvas()
            self.refresh_props()

    def canvas_drag(self, event):
        ex, ey = (event.x, event.y)

        if self.selected_object:
            geom = self.canvas.winfo_geometry()
            w, rest = geom.split("x")
            h = rest.split("+")[0]
            w = int(w); h = int(h)
            x = self.canvas.winfo_rootx() - self.mainwindow.winfo_x()
            y = self.canvas.winfo_rooty() - self.mainwindow.winfo_y()

            ox = self.selected_object.drag_offset[0]
            oy = self.selected_object.drag_offset[1]
            ow = self.selected_object.w - ox + 2
            oh = self.selected_object.h - oy + 2

            dirty = False
            if ex < 0 + ox:
                ex = 0 + ox
                dirty = True
            if ey < 0 + oy:
                ey = 0 + oy
                dirty = True
            if ex > w - ow:
                ex = w - ow
                dirty = True
            if ey > h - oh:
                ey = h - oh
                dirty = True
            if dirty:
                self.mainwindow.event_generate("<Motion>", when="tail", x=x+ex, y=y+ey, warp=1)

            self.selected_object.x = ex - self.selected_object.drag_offset[0]
            self.selected_object.y = ey - self.selected_object.drag_offset[1]
            self.refresh_canvas()
            self.refresh_props()

    def canvas_right_click(self, event):
        self.selected_object = None
        self.refresh_tree()
        self.refresh_canvas()
        self.refresh_props()

    def refresh_tree(self):
        self.object_tree.delete(*self.object_tree.get_children())
        for object in self.objects:
            object.tree_id = self.object_tree.insert("", "end", text=object.id, values=(type(object).__name__, object.variant, object.enabled))

        if self.selected_object:
            self.object_tree.focus(self.selected_object.tree_id)
            self.object_tree.selection_set(self.selected_object.tree_id)
        else:
            if len(self.object_tree.selection()) > 0:
                self.object_tree.selection_remove(self.object_tree.selection()[0])

    def refresh_canvas(self):
        for object in self.objects:
            object.selected = False
        if self.selected_object:
            if self.selected_object.enabled:
                self.selected_object.selected = True

        canvas = self.canvas
        canvas.delete(tk.ALL)

        for object in self.objects:
            if object.enabled:
                object.draw(canvas)

    def refresh_props(self):
        for name, prop in self.properties.items():
            if isinstance(prop, tk.Canvas):
                prop.config(bg="#dadada")
            try:
                prop.state(["disabled"])
            except AttributeError:
                pass

        if self.selected_object:
            self.selected_object.set_props(self.properties)

        if self.selected_object:
            for button in self.sel_buttons:
                button.state(["!disabled"])
        else:
            for button in self.sel_buttons:
                button.state(["disabled"])

    def id_unfocus_callback(self, event):
        if self.selected_object:
            self.selected_object.id = self.builder.get_variable("prop_id_var").get()
            self.refresh_tree()
            self.refresh_canvas()
            self.selected_object.set_props(self.properties)

    def tint_unfocus_callback(self, event):
        if self.selected_object:
            new_tint = self.builder.get_variable("prop_tint_var").get()
            if re.match("^#[0-9A-Fa-f]{6}$", new_tint):
                self.selected_object.tint = new_tint
                self.selected_object.set_props(self.properties)

    def variant_unfocus_callback(self, event):
        if self.selected_object:
            new_variant = self.builder.get_variable("prop_variant_var").get().strip()
            new_variant = re.sub("[^A-Za-z0-9-_]", "", new_variant)
            if new_variant:
                self.selected_object.variant = new_variant
            else:
                self.selected_object.variant = "default"
            self.selected_object.set_props(self.properties)
            self.refresh_tree()

    def prop_enabled_callback(self):
        if self.selected_object:
            self.selected_object.enabled = self.builder.get_variable("prop_enabled_var").get()
            self.selected_object.set_props(self.properties)
            self.refresh_tree()

    def x_change_callback(self):
        self.selected_object.x = self.builder.get_variable("prop_x_var").get()
        self.refresh_canvas()
        self.selected_object.set_props(self.properties)

    def y_change_callback(self):
        self.selected_object.y = self.builder.get_variable("prop_y_var").get()
        self.refresh_canvas()
        self.selected_object.set_props(self.properties)

    def image_select_callback(self):
        selection = tkfd.askopenfilename(filetypes=(("png files", "*.png"),("all files","*.*")), initialdir=self.img_root)
        if len(selection) > 0:
            if not selection.startswith(self.img_root):
                tkmb.showerror("Invalid Path", f"Selected file '{selection}' invalid (not child of image root)")
            self.selected_object.image_path = selection[len(self.img_root) + 1:]
            self.selected_object.image_real_path = selection
            self.selected_object.refresh_image()
            self.selected_object.set_props(self.properties)
            self.refresh_canvas()

    def tree_select_callback(self, something):
        tree = self.object_tree

        if len(tree.selection()) == 0:
            return

        for object in self.objects:
            if object.tree_id == tree.selection()[0]:
                break

        self.selected_object = object
        self.refresh_canvas()
        self.refresh_props()


if __name__ == "__main__" :
    app = LayoutApp()
    app.run()
