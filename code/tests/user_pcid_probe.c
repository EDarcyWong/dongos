#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define SYSV __attribute__((sysv_abi))
extern uint64_t SYSV user_pcid_bind(uint64_t,uint64_t,uint64_t),user_pcid_unbind(uint64_t,uint64_t),user_pcid_operand(uint64_t);
extern uint64_t user_pcid_enabled,user_pcid_bindings[16][3],user_pcid_retained;
extern uint64_t SYSV user_entropy64(uint64_t*,uint64_t*);
void* SYSV dong_user_dispatch(void*p){(void)p;return NULL;}
static unsigned checks;
#define CHECK(x) do{++checks;if(!(x)){fprintf(stderr,"PCID operand failed line %u\n",__LINE__);return 1;}}while(0)
int main(void){
 const uint64_t nf=UINT64_C(1)<<63;
 for(unsigned id=0;id<16;id++){
  const uint64_t root=0x100000+(uint64_t)id*32*4096;
  CHECK(user_pcid_bind(id,root,1)==1&&user_pcid_bindings[id][0]==root&&user_pcid_bindings[id][1]==1);
  CHECK(user_pcid_operand(root)==root&&user_pcid_bindings[id][2]==0);
  user_pcid_enabled=1;
  CHECK(user_pcid_operand(root)==(root|(id+1)));
  CHECK(user_pcid_operand(root)==(nf|root|(id+1)));
  user_pcid_enabled=0;
 }
 uint64_t snapshot[16][3];memcpy(snapshot,user_pcid_bindings,sizeof snapshot);
 CHECK(!user_pcid_bind(16,0x100000,1)&&!user_pcid_bind(0,0,2)&&!user_pcid_bind(0,1,2));
 CHECK(!user_pcid_bind(0,UINT64_C(0x100000000),2)&&!user_pcid_bind(0,0x100000,0));
 CHECK(!user_pcid_bind(0,0x100000,1)&&!memcmp(snapshot,user_pcid_bindings,sizeof snapshot));
 for(unsigned gen=2;gen<10002;gen++){
  uint64_t root=(gen%2?0x300000:0x100000);
  CHECK(user_pcid_bind(0,root,gen)==1&&user_pcid_bindings[0][2]==0);
  user_pcid_enabled=1;
  CHECK(user_pcid_operand(root)==(root|1));
  CHECK(user_pcid_operand(root)==(nf|root|1));
  CHECK(user_pcid_operand(0x900000)==0x900000);
  user_pcid_enabled=0;
  CHECK(user_pcid_unbind(0,root)==1&&user_pcid_bindings[0][0]==0&&user_pcid_bindings[0][2]==0);
  CHECK(!user_pcid_bind(0,root,gen));
 }
 CHECK(user_pcid_retained==10016);
 uint64_t value=UINT64_C(0x1234abcddcba4321),kind=77;
 CHECK(!user_entropy64(NULL,&kind)&&kind==77);
 CHECK(!user_entropy64(&value,NULL)&&value==UINT64_C(0x1234abcddcba4321));
 unsigned actual=0;uint64_t actual_kind=0;
 for(unsigned n=0;n<16;n++){
  uint64_t before=value,source_before=kind;uint64_t ok=user_entropy64(&value,&kind);
  if(ok){CHECK(kind==1||kind==2);++actual;actual_kind=kind;}
  else CHECK(value==before&&kind==source_before);
 }
 printf("user PCID operand checks passed %u; privileged CR3/INVPCID not executed; host DRNG successes=%u source=%u\n",checks,actual,(unsigned)actual_kind);return 0;
}
