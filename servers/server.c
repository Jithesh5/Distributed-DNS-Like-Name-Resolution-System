#define _POSIX_C_SOURCE 200809L
#include <arpa/inet.h>
#include <netinet/in.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>
#define BUF_SIZE 512
static void respond(int fd,const struct sockaddr_in *client,socklen_t clen,const char *domain,const char *file) {
 FILE *fp=fopen(file,"r");if(!fp){const char *m="ERROR 0";sendto(fd,m,strlen(m),0,(const struct sockaddr*)client,clen);perror("fopen");return;}
 char name[256],ip[64],found[64]={0};
 while(fscanf(fp,"%255s %63s",name,ip)==2)if(!strcmp(name,domain)){snprintf(found,sizeof(found),"%s",ip);break;}
 fclose(fp);char out[BUF_SIZE];
 if(found[0]){snprintf(out,sizeof(out),"OK %s 10",found);printf("QUERY %s -> %s\n",domain,found);}
 else{snprintf(out,sizeof(out),"NOT_FOUND - 0");printf("QUERY %s -> NOT_FOUND\n",domain);}
 sendto(fd,out,strlen(out),0,(const struct sockaddr*)client,clen);
}
int main(int argc,char **argv) {
 if(argc!=3){fprintf(stderr,"Usage: %s <port> <mapping-file>\n",argv[0]);return 1;}
 int port=atoi(argv[1]);if(port<1||port>65535){fprintf(stderr,"Invalid port\n");return 1;}
 int fd=socket(AF_INET,SOCK_DGRAM,0);if(fd<0){perror("socket");return 1;}
 int reuse=1;setsockopt(fd,SOL_SOCKET,SO_REUSEADDR,&reuse,sizeof(reuse));
 struct sockaddr_in addr;memset(&addr,0,sizeof(addr));addr.sin_family=AF_INET;addr.sin_addr.s_addr=htonl(INADDR_ANY);addr.sin_port=htons((unsigned short)port);
 if(bind(fd,(struct sockaddr*)&addr,sizeof(addr))<0){perror("bind");close(fd);return 1;}
 printf("UDP resolver listening on port %d using %s\n",port,argv[2]);
 for(;;){char buf[BUF_SIZE];struct sockaddr_in c;socklen_t cl=sizeof(c);ssize_t n=recvfrom(fd,buf,sizeof(buf)-1,0,(struct sockaddr*)&c,&cl);if(n<0){perror("recvfrom");continue;}buf[n]='\0';
  char cmd[32]={0},domain[256]={0};
  if(sscanf(buf,"%31s %255s",cmd,domain)!=2||strcmp(cmd,"QUERY")){const char *m="BAD_REQUEST - 0";sendto(fd,m,strlen(m),0,(struct sockaddr*)&c,cl);continue;}
  respond(fd,&c,cl,domain,argv[2]);
 }
}
