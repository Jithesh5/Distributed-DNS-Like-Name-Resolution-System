CC=gcc
CFLAGS=-Wall -Wextra -Wpedantic -O2
all: dns_client dns_server
dns_client: client/client.c
	$(CC) $(CFLAGS) -o dns_client client/client.c
dns_server: servers/server.c
	$(CC) $(CFLAGS) -o dns_server servers/server.c
clean:
	rm -f dns_client dns_server
.PHONY: all clean
