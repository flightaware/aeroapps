objects = $(wildcard *.in)
outputs := $(objects:.in=.txt)

.PHONY: all
all: $(outputs)

%.txt: %.in
	. ../venv/bin/activate && pip-compile --verbose --build-isolation --output-file $@ $<

test.txt: base.txt
dev.txt: test.txt
