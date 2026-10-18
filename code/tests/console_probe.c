#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#define ABI __attribute__((sysv_abi))
#else
#include <pthread.h>
#include <sched.h>
#define ABI
#endif
typedef uint64_t U;
typedef struct {U head,tail,dropped;unsigned char bytes[256];} Queue;
typedef struct {U enabled;} State;
typedef struct {U kind,code;int64_t value,modifiers;} Event;
_Static_assert(sizeof(Queue)==280,"console queue");
extern ABI U con_init(Queue*),con_push(Queue*,unsigned char,U*),con_pop(Queue*,unsigned char*,U*),con_key(State*,Queue*,const Event*,U*);
extern ABI unsigned char con_ascii(U,U);
static U checks;
#define CK(x) do{checks++;if(!(x)){fprintf(stderr,"console check failed line %d: %s\n",__LINE__,#x);exit(1);}}while(0)
static const U INVALID=0x07350001,EXHAUSTED=0x07350002;
static void queues(void){Queue q;U present;unsigned char b=0xa5;CK(con_init(&q)==0);CK(con_pop(&q,&b,&present)==0&&!present&&b==0xa5);for(U round=0;round<1000;round++){for(U i=0;i<256;i++){CK(con_push(&q,(unsigned char)(i+round),&present)==0&&present);}Queue before=q;CK(con_push(&q,0x5a,&present)==0&&!present&&q.dropped==before.dropped+1);CK(!memcmp(q.bytes,before.bytes,256)&&q.head==before.head&&q.tail==before.tail);for(U i=0;i<256;i++){CK(con_pop(&q,&b,&present)==0&&present&&b==(unsigned char)(i+round));}}Queue before=q;present=0xa5;q.head=q.tail+1;Queue invalid=q;CK(con_push(&q,1,&present)==INVALID&&!memcmp(&invalid,&q,sizeof q)&&present==0xa5);CK(con_pop(&q,&b,&present)==INVALID&&!memcmp(&invalid,&q,sizeof q));q=before;q.tail=q.head+257;invalid=q;CK(con_push(&q,1,&present)==INVALID&&!memcmp(&invalid,&q,sizeof q));q=before;q.head=q.tail=UINT64_MAX-1;CK(con_push(&q,'x',&present)==0&&present&&q.tail==UINT64_MAX);CK(con_pop(&q,&b,&present)==0&&present&&b=='x'&&q.head==UINT64_MAX);before=q;CK(con_push(&q,'y',&present)==EXHAUSTED&&!memcmp(&before,&q,sizeof q));CK(con_pop(&q,&b,&present)==0&&!present);q.head=0;q.tail=256;q.dropped=UINT64_MAX;before=q;CK(con_push(&q,1,&present)==0&&!present&&!memcmp(&before,&q,sizeof q));CK(con_init(NULL)==INVALID);}
typedef struct {unsigned code;unsigned char plain,shifted;} Key;
static const Key keys[]={
 {2,'1','!'},{3,'2','@'},{4,'3','#'},{5,'4','$'},{6,'5','%'},{7,'6','^'},{8,'7','&'},{9,'8','*'},{10,'9','('},{11,'0',')'},
 {12,'-','_'},{13,'=','+'},{14,8,8},{15,9,9},{16,'q','Q'},{17,'w','W'},{18,'e','E'},{19,'r','R'},{20,'t','T'},{21,'y','Y'},{22,'u','U'},{23,'i','I'},{24,'o','O'},{25,'p','P'},
 {26,'[','{'},{27,']','}'},{28,13,13},{30,'a','A'},{31,'s','S'},{32,'d','D'},{33,'f','F'},{34,'g','G'},{35,'h','H'},{36,'j','J'},{37,'k','K'},{38,'l','L'},
 {39,';',':'},{40,'\'','"'},{41,'`','~'},{43,'\\','|'},{44,'z','Z'},{45,'x','X'},{46,'c','C'},{47,'v','V'},{48,'b','B'},{49,'n','N'},{50,'m','M'},
 {51,',','<'},{52,'.','>'},{53,'/','?'},{57,' ',' '},{96,13,13},{98,'/','/'}};
static void mapping(void){U mods[]={0,1,2,3,256,257,258,4,8,16,32,64,128,1024,512};for(U code=0;code<768;code++)for(unsigned m=0;m<sizeof mods/sizeof mods[0];m++){unsigned char expected=0;for(unsigned i=0;i<sizeof keys/sizeof keys[0];i++)if(keys[i].code==code){unsigned char ch=keys[i].plain;if(mods[m]&0xf0)expected=0;else if(ch>='a'&&ch<='z'){if(mods[m]&12)expected=ch-96;else expected=((!!(mods[m]&3))^(!!(mods[m]&256)))?keys[i].shifted:ch;}else if(!(mods[m]&12))expected=(mods[m]&3)?keys[i].shifted:ch;}CK(con_ascii(code,mods[m])==expected);}Queue q;CK(con_init(&q)==0);State s={0};U route,present;Event e={1,30,1,0};CK(con_key(&s,&q,&e,&route)==0&&route==0&&q.tail==0);e.code=88;CK(con_key(&s,&q,&e,&route)==0&&route==2&&s.enabled==1);e.value=2;CK(con_key(&s,&q,&e,&route)==0&&route==1&&s.enabled==1);e.value=0;CK(con_key(&s,&q,&e,&route)==0&&route==1&&s.enabled==1);e=(Event){1,30,1,257};CK(con_key(&s,&q,&e,&route)==0&&route==1);unsigned char b;CK(con_pop(&q,&b,&present)==0&&present&&b=='a');e=(Event){1,88,1,0};CK(con_key(&s,&q,&e,&route)==0&&route==3&&s.enabled==0);e=(Event){2,0,1,1};CK(con_key(&s,&q,&e,&route)==0&&route==0);}
static Queue concurrent;
static void pause_thread(void){
#ifdef _WIN32
 SwitchToThread();
#else
 sched_yield();
#endif
}
#ifdef _WIN32
static DWORD WINAPI producer(LPVOID ignored){
#else
static void*producer(void*ignored){
#endif
 (void)ignored;for(U i=0;i<100000;i++){U inserted=0;while(!inserted){if(con_push(&concurrent,(unsigned char)(i*37),&inserted))exit(2);if(!inserted)pause_thread();}}
#ifdef _WIN32
 return 0;
#else
 return NULL;
#endif
}
static void concurrency(void){CK(con_init(&concurrent)==0);
#ifdef _WIN32
 HANDLE thread=CreateThread(NULL,0,producer,NULL,0,NULL);CK(thread!=NULL);
#else
 pthread_t thread;CK(pthread_create(&thread,NULL,producer,NULL)==0);
#endif
 for(U i=0;i<100000;i++){U present=0;unsigned char b=0;while(!present){CK(con_pop(&concurrent,&b,&present)==0);if(!present)pause_thread();}CK(b==(unsigned char)(i*37));}
#ifdef _WIN32
 CK(WaitForSingleObject(thread,10000)==WAIT_OBJECT_0);CloseHandle(thread);
#else
 CK(pthread_join(thread,NULL)==0);
#endif
 CK(concurrent.head==100000&&concurrent.tail==100000);
}
ABI void __dong_panic(void){fprintf(stderr,"unexpected console Dong panic\n");exit(2);}
int main(void){queues();mapping();concurrency();printf("console native checks passed %lu; wrap_cycles=1000; concurrent_bytes=100000; F12=ok\n",(unsigned long)checks);return 0;}
