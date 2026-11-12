#define _POSIX_C_SOURCE 200809L
#include <arpa/inet.h>
#include <netinet/in.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <time.h>
#include <unistd.h>
#define BUF_SIZE 512
#define CACHE_SIZE 128
#define MAX_SERVERS 8
typedef struct { char name[256]; char ip[64]; time_t expires; int valid; } CacheEntry;
typedef struct { struct sockaddr_in addr; char ip[INET_ADDRSTRLEN]; int port; } Server;
static CacheEntry cache[CACHE_SIZE];
static Server servers[MAX_SERVERS];
static int server_count;
static FILE *log_file;
static double now_ms(void) { struct timespec ts; clock_gettime(CLOCK_MONOTONIC,&ts); return ts.tv_sec*1000.0+ts.tv_nsec/1000000.0; }
static void log_result(const char *d,const char *s,const char *src,double ms,int si) {
 if(log_file){fprintf(log_file,"%s,%s,%s,%.3f,%d\n",d,s,src,ms,si>=0?si+1:0);fflush(log_file);}
}
static int cache_get(const char *name,char *ip,size_t n) {
 time_t now=time(NULL);
 for(int i=0;i<CACHE_SIZE;i++){
  if(cache[i].valid && cache[i].expires<=now) cache[i].valid=0;
  if(cache[i].valid && !strcmp(cache[i].name,name)){snprintf(ip,n,"%s",cache[i].ip);return 1;}
 }
 return 0;
}
static void cache_put(const char *name,const char *ip,int ttl) {
 int slot=-1;
 for(int i=0;i<CACHE_SIZE;i++) if(!cache[i].valid){slot=i;break;}
 if(slot<0){slot=0;for(int i=1;i<CACHE_SIZE;i++)if(cache[i].expires<cache[slot].expires)slot=i;}
 snprintf(cache[slot].name,sizeof(cache[slot].name),"%s",name);
 snprintf(cache[slot].ip,sizeof(cache[slot].ip),"%s",ip);
 cache[slot].expires=time(NULL)+(ttl>0?ttl:10);cache[slot].valid=1;
}
static int add_server(const char *ip,int port) {
 if(server_count>=MAX_SERVERS||port<1||port>65535)return -1;
 Server *s=&servers[server_count];memset(s,0,sizeof(*s));
 s->addr.sin_family=AF_INET;s->addr.sin_port=htons((unsigned short)port);
 if(inet_pton(AF_INET,ip,&s->addr.sin_addr)!=1)return -1;
 snprintf(s->ip,sizeof(s->ip),"%s",ip);s->port=port;server_count++;return 0;
}
static int query_server(int fd,int idx,const char *domain,char *response,size_t cap,double *elapsed) {
 char req[BUF_SIZE];snprintf(req,sizeof(req),"QUERY %s",domain);Server *s=&servers[idx];
 for(int attempt=1;attempt<=2;attempt++){
  double start=now_ms();
  if(sendto(fd,req,strlen(req),0,(struct sockaddr*)&s->addr,sizeof(s->addr))<0)continue;
  struct sockaddr_in from;socklen_t fl=sizeof(from);
  ssize_t n=recvfrom(fd,response,cap-1,0,(struct sockaddr*)&from,&fl);
  if(n>=0){response[n]='\0';*elapsed+=now_ms()-start;return 1;}
  *elapsed+=now_ms()-start;
  if(attempt==1)fprintf(stderr,"Server %s:%d timed out; retrying once\n",s->ip,s->port);
 }
 return 0;
}
static void resolve(int fd,const char *domain) {
 char ip[64]={0};
 if(cache_get(domain,ip,sizeof(ip))){printf("RESULT domain=%s status=OK ip=%s source=CACHE latency_ms=0.000\n",domain,ip);log_result(domain,"OK","CACHE",0,-1);return;}
 double total=0;char response[BUF_SIZE]={0};int last_server=-1;int saw_not_found=0;
 for(int i=0;i<server_count;i++){
  last_server=i;
  if(!query_server(fd,i,domain,response,sizeof(response),&total)){
   fprintf(stderr,"Server %s:%d failed; trying next server\n",servers[i].ip,servers[i].port);continue;
  }
  char status[32]={0},rip[64]={0};int ttl=10;
  int fields=sscanf(response,"%31s %63s %d",status,rip,&ttl);
  if(fields>=2&&!strcmp(status,"OK")){
   cache_put(domain,rip,ttl);printf("RESULT domain=%s status=OK ip=%s source=SERVER%d latency_ms=%.3f\n",domain,rip,i+1,total);
   log_result(domain,"OK","SERVER",total,i);return;
  }
  if(fields>=1&&!strcmp(status,"NOT_FOUND")){saw_not_found=1;continue;}
  fprintf(stderr,"Unexpected response from server %d: %s\n",i+1,response);
 }
 if(saw_not_found){printf("RESULT domain=%s status=NOT_FOUND latency_ms=%.3f\n",domain,total);log_result(domain,"NOT_FOUND","SERVERS",total,last_server);}
 else {printf("RESULT domain=%s status=ALL_SERVERS_FAILED latency_ms=%.3f\n",domain,total);log_result(domain,"ALL_SERVERS_FAILED","NONE",total,-1);}
}
int main(int argc,char **argv) {
 if(argc<4||(argc-2)%2!=0){fprintf(stderr,"Usage: %s <log.csv> <server-ip> <server-port> [<server-ip> <server-port> ...]\n",argv[0]);return 1;}
 for(int i=2;i<argc;i+=2)if(add_server(argv[i],atoi(argv[i+1]))){fprintf(stderr,"Invalid server %s:%s\n",argv[i],argv[i+1]);return 1;}
 log_file=fopen(argv[1],"a");if(!log_file){perror("open log");return 1;}
 if(ftell(log_file)==0)fprintf(log_file,"domain,status,source,latency_ms,server_number\n");
 int fd=socket(AF_INET,SOCK_DGRAM,0);if(fd<0){perror("socket");fclose(log_file);return 1;}
 struct timeval tv={.tv_sec=1,.tv_usec=0};
 if(setsockopt(fd,SOL_SOCKET,SO_RCVTIMEO,&tv,sizeof(tv))<0){perror("setsockopt");close(fd);fclose(log_file);return 1;}
 printf("Interactive resolver client ready. Enter a domain, or type 'quit'.\n");
 char line[256];
 while(printf("dns> "),fflush(stdout),fgets(line,sizeof(line),stdin)){
  line[strcspn(line,"\r\n")]='\0';if(!strcmp(line,"quit")||!strcmp(line,"exit"))break;if(!line[0])continue;
  if(strchr(line,' ')||strchr(line,'\t')){puts("Enter one domain name without spaces.");continue;}
  resolve(fd,line);
 }
 close(fd);fclose(log_file);return 0;
}
