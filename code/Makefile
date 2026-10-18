# Windows can use the same commands directly via `python tools/build.py ...`.
PYTHON ?= python3
USB_IMAGE ?= build/usb/dongos.img

.PHONY: all run debug test doctor usb
all:
	$(PYTHON) tools/build.py build

run:
	$(PYTHON) tools/build.py run

debug:
	$(PYTHON) tools/build.py debug

test:
	$(PYTHON) tools/build.py test

doctor:
	$(PYTHON) tools/build.py doctor

# Produces a new ordinary file. Writing a physical device is a separate step.
usb:
	$(PYTHON) -m tools.build_usb --output "$(USB_IMAGE)"
