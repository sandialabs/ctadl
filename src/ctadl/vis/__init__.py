color_reset = "\u001b[0m"
color_fg = []
color_bg = []

for i in range(0, 16):
    for j in range(0, 16):
        code = str(i * 16 + j)
        color_fg.append("\u001b[38;5;" + code + "m")

for i in range(0, 16):
    for j in range(0, 16):
        code = str(i * 16 + j)
        color_bg.append("\u001b[48;5;" + code + "m")
