all:
	@echo "Use 'make pull' or 'make push'"


pull:
	rsync --archive --no-perms --verbose "berlios:/home/groups/sonata/htdocs/" . --exclude "usage"

push:
	rsync --archive --no-perms --omit-dir-times --verbose . "berlios:/home/groups/sonata/htdocs/" --exclude=".git" --exclude="Makefile"
