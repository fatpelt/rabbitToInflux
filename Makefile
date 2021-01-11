commit = $(shell git log --oneline -1 | awk '{print $$1'})
ifeq "${BUILD_NUMBER}" ""
build = .0
else
build = .${BUILD_NUMBER}
endif

all: deb 

deb:
	mkdir -p rabbitToInflux/usr/local/etc/rabbitToInflux/
	mkdir -p rabbitToInflux/usr/local/bin/rabbitToInflux/
	mkdir -p rabbitToInflux/etc/init.d
	mkdir -p rabbitToInflux/etc/systemd/system
	mkdir -p rabbitToInflux/DEBIAN

	cp -a postinst rabbitToInflux/DEBIAN/

	cp *.py rabbitToInflux/usr/local/bin/rabbitToInflux/

	cp rabbitToInflux.service rabbitToInflux/etc/systemd/system/

	cp main.conf rabbitToInflux/usr/local/etc/rabbitToInflux/
	cp EXAMPLE.conf rabbitToInflux/usr/local/etc/rabbitToInflux/
	cp LICENSE rabbitToInflux/usr/local/etc/rabbitToInflux/
	cp requirements.txt rabbitToInflux/usr/local/etc/rabbitToInflux/
	cp sfacctd.conf.example rabbitToInflux/usr/local/etc/rabbitToInflux/

	sed 's/COMMIT/${commit}/' control > rabbitToInflux/DEBIAN/control
	sed -i 's/BUILD/${build}/' rabbitToInflux/DEBIAN/control
	cd rabbitToInflux ; find usr/local/etc/rabbitToInflux/ -type f > DEBIAN/conffiles

	fakeroot dpkg-deb --build rabbitToInflux .

clean:
	-rm -fr rabbitToInflux/
	-rm -f *.deb
