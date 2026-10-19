# dmgbuild settings - used by packaging/build.sh:
#   dmgbuild -s packaging/dmg_settings.py -D app=... -D guide=... -D background=... -D icon=... "Volume" out.dmg
# Icon positions must match packaging/make_dmg_background.py.
import os.path

app = defines["app"]  # noqa: F821 (provided by dmgbuild)
guide = defines["guide"]  # noqa: F821
app_name = os.path.basename(app)
guide_name = os.path.basename(guide)

format = "UDZO"
compression_level = 9
files = [app, guide]
symlinks = {"Applications": "/Applications"}
icon = defines.get("icon")  # noqa: F821  volume icon
background = defines["background"]  # noqa: F821  background.png (+ background@2x.png)

window_rect = ((200, 120), (660, 500))
default_view = "icon-view"
show_status_bar = False
show_tab_view = False
show_toolbar = False
show_pathbar = False
show_sidebar = False
icon_size = 104
text_size = 13
icon_locations = {
    app_name: (165, 175),
    "Applications": (495, 175),
    guide_name: (330, 330),
}
hide_extensions = [guide_name]
