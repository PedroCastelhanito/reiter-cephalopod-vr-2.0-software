"""Draw retained rig inputs using the current production corner calculation."""

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from cephvr.gui.projector_geometry import RigDimensions, resolved_screens, screen_corners

OUT = Path(__file__).resolve().parent
rig = RigDimensions(120, 166, 110, (60, 93, 53))
drafts = {
    "Front": dict(width="94", height="85", subject_distance="74.5"),
    "Left": dict(width="126", height="85", subject_distance="51"),
    "Right": dict(width="126", height="85"),
    "Bottom": dict(width="126", height="94", subject_distance="51"),
}
drafts = resolved_screens(rig, drafts)
planes = {
    face: screen_corners(
        rig, face, values, front_distance="74.5", bottom_distance="51"
    )
    for face, values in drafts.items()
}
assert min(p[2] for p in planes["Front"]) - planes["Bottom"][0][2] == 5
assert min(p[1] for p in planes["Bottom"]) - planes["Front"][0][1] == 5
assert planes["Bottom"][1][1] - planes["Bottom"][0][1] == 126
assert planes["Bottom"][3][0] - planes["Bottom"][0][0] == -94

S = 2
im = Image.new("RGB", (1600*S, 1050*S), "#f7f9fc")
d = ImageDraw.Draw(im)
ink, muted, tank = "#1b2c42", "#596b80", "#a8b6c6"
colors = {"Front": "#2677c5", "Left": "#149185", "Right": "#db792e", "Bottom": "#7b53bb"}

def font(size, bold=False):
    return ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf", int(size*S))

def text(x, y, content, size=20, color=ink, bold=False):
    d.text((x*S,y*S), content, font=font(size,bold), fill=color)

def line(points, color=ink, width=2):
    d.line([(int(x*S),int(y*S)) for x,y in points], fill=color, width=int(width*S))

def poly(points, color, alpha=45):
    overlay = Image.new("RGBA", im.size)
    od = ImageDraw.Draw(overlay)
    from PIL import ImageColor
    od.polygon([(int(x*S),int(y*S)) for x,y in points], fill=(*ImageColor.getrgb(color),alpha))
    im.paste(overlay,(0,0),overlay)
    line(points+[points[0]],color,2.3)

def dot(point,color=ink,r=5):
    x,y=point
    d.ellipse(((x-r)*S,(y-r)*S,(x+r)*S,(y+r)*S),fill=color)

text(55,25,"Tank & usable screens",34,bold=True)
text(55,76,"Bottom image: 126 mm width × 94 mm height   ·   Frame gaps: 5 mm at front and lower junctions",21)
text(55,113,"Last saved rig dimensions/distances + updated screen geometry; all coordinates in millimetres",17,muted)
line([(55,150),(1545,150)],tank,1)
text(55,178,"3D view",25,bold=True)
text(55,216,"Colored areas are usable screens; gray edges are the tank.",17,muted)

def iso(p):
    x,y,z=p
    return (435+2.7*(x-.72*y),580+.8*x+.58*y-2.65*z)

corners=[(x,y,z) for x in (0,120) for y in (0,166) for z in (0,110)]
for a in corners:
    for b in corners:
        if a<b and sum(u!=v for u,v in zip(a,b))==1:
            line([iso(a),iso(b)],tank,1.5)
for face in ("Bottom","Left","Right","Front"):
    poly([iso(p) for p in planes[face]],colors[face],45)
subject=iso(rig.subject)
dot(subject)
line([subject,(580,435)],ink,1)
text(589,417,"Subject",20,bold=True)
text(589,446,"(60, 93, 53)",17,muted)
for face,pos,anchor in (
    ("Front",(666,275),planes["Front"][2]),
    ("Left",(75,360),planes["Left"][2]),
    ("Right",(670,529),planes["Right"][1]),
    ("Bottom",(220,729),planes["Bottom"][3]),
):
    x,y=pos
    line([iso(anchor),(x+25,y-5)],colors[face],1)
    text(x,y,face,22,colors[face],True)
text(55,799,"Image axes on Bottom",20,bold=True)
text(55,833,"X / width: 126 mm toward the tank back (+rig Y)",19)
text(55,865,"Y / height: 94 mm across the tank (−rig X)",19)

text(900,178,"Top view",25,bold=True)
def top(p):
    return (938+1.85*p[0],545-1.85*p[1])
line([top((0,0)),top((120,0)),top((120,166)),top((0,166)),top((0,0))],tank,1.5)
poly([top(p) for p in planes["Bottom"]],colors["Bottom"],38)
for face in ("Front","Left","Right"):
    unique=list(dict.fromkeys(top(p) for p in planes[face]))
    line(unique,colors[face],3)
dot(top(rig.subject),r=4)
text(943,558,"Tank width 120",17,muted)
text(900,221,"Back",16,muted)
text(888,518,"Front",16,muted)
text(1220,235,"Bottom footprint",21,colors["Bottom"],True)
text(1220,273,"94 mm across tank",19)
text(1220,305,"126 mm front to back",19)
text(1220,350,"5 mm front gap",20,bold=True)
line([top((107,21)),(1190,373),(1210,373)],ink,1)
text(1220,412,"Lateral clearance: 4 mm",18,muted)
text(1220,441,"from retained side distances",16,muted)

text(900,610,"Side view",25,bold=True)
def side(p):
    return (935+3.1*p[1],951-2.25*p[2])
line([side((0,0,0)),side((0,166,0)),side((0,166,110)),side((0,0,110)),side((0,0,0))],tank,1.5)
poly([side(p) for p in planes["Left"]],colors["Left"],35)
line([side(planes["Front"][0]),side(planes["Front"][3])],colors["Front"],3)
line([side(planes["Bottom"][0]),side(planes["Bottom"][1])],colors["Bottom"],3)
dot(side(rig.subject),r=4)
text(1030,701,"Left / Right usable area",19,colors["Left"],True)
text(1030,777,"126 × 85 mm",19)
text(1010,964,"Tank depth 166",17,muted)
line([side((0,143,4.5)),(1490,911)],ink,1)
text(1440,860,"5 mm",20,bold=True)
text(1440,888,"lower gap",16,muted)

line([(55,917),(810,917)],tank,1)
text(55,939,"Tank 120 × 166 × 110 mm   |   Front 94 × 85 mm",18)
text(55,973,"Wall lower edge Z = 7 mm; Bottom plane Z = 2 mm",18)
text(55,1007,"Front plane Y = 18.5 mm; side/Bottom front edges Y = 23.5 mm",16,muted)
im.save(OUT/"tank-screens.png")
data={"date":"2026-10-14","source":"Current production screen_corners/resolved_screens; last retained rig/profile inputs, not live optical measurements","tank_mm":[120,166,110],"subject_mm":rig.subject,"screen_inputs":drafts,"corners_mm":planes,"frame_front_lower_gap_mm":5,"lateral_clearance_mm":4,"limitations":"Saved distances51mm plus94mm floor cross-span yield4mm lateral clearance; no automatic side-distance adjustment. Plot is geometry only; no projected coverage/optical acceptance."}
(OUT/"geometry.json").write_text(json.dumps(data,indent=2)+"\n",encoding="utf-8")
print(OUT/"tank-screens.png")
