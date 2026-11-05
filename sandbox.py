import threading
import time
from typing import Optional,Dict,List,Tuple
from opensandbox.sync.sandbox import SandboxSync
from deepagents_opensandbox import OpensandboxBackend
import  logging

logger=logging.getLogger(__name__)

from config_settings import settings

class _SandboxEntry:
    def __init__(self,sandbox:SandboxSync,backend:OpensandboxBackend):
        self.sandbox = sandbox
        self.backend = backend
        self.last_used_at=time.time()
        self.lock = threading.Lock()
        self.provisioned=False #标识初始化是否成功
        self.provisioning_error:Optional[str]=None

    def touch(self) :# 更新时间
        self.last_used_at=time.time()

    @property
    def idle_seconds(self):#根据当前时间和最后使用的时间差
        return time.time() - self.last_used_at

    def close(self):#回收当前沙箱对象
        try:
            self.sandbox.kill()
        except Exception:
            pass
        try:
            self.sandbox.close()
        except Exception:
            pass



class SandboxManager:
      def __init__(self,image:str,idle_timeout:int=settings.SANDBOX_IDLE_TIMEOUT,cleanup_interval:int=settings.SANDBOX_CLEANUP_INTERVAL):
          self._image=image
          self._idle_timeout=idle_timeout
          self._cleanup_interval=cleanup_interval
          self._entries:Dict[str,_SandboxEntry]={}
          self._global_lock=threading.Lock()
          self._stop_event=threading.Event()
          self._cleanup_thread:Optional[threading.Thread]=None
          self._available=False

     # 程序启动时验证沙箱是否可用
      def start(self):
          probe=None
          try:
              logger.info("SandboxManager :沙箱激活")
              probe=SandboxSync.create(self._image)# 创建沙箱
              probe.kill()
              probe.close()
              self._available=True
              logger.info("SandboxManager:沙箱 开始清除线程")
          except Exception as e:
              logger.warning(f"SandboxManager: 沙箱激活异常-{e}")
              self._available=False
              return

          self._cleanup_thread=threading.Thread(
              target=self._cleanup_loop,name="Sandbox-Cleanup-Thread",daemon=True
          )
          self._cleanup_thread.start()

      def stop(self):
          self._stop_event.set()
          if self._cleanup_thread and self._cleanup_thread.is_alive():
              self._cleanup_thread.join(timeout=5)

          with self._global_lock:
              entries=list(self._entries.values())
              self._entries.clear()
          for e in entries:
              with e.lock:
                   e.close()
          logger.info(f"SandboxManager :stopped ,cleanup up {len(entries)} sandbox(es)")

      @property
      def available(self)->bool:
          return self._available

      def _cleanup_loop(self):
          logger.info(f"SandboxManager: cleaning up "
                      f"idle_timeout={self._idle_timeout}s,idle_timeout={self._cleanup_interval}s")

          while not self._stop_event.is_set():
              try:
                  self._reap_expired()
              except Exception as e:
                  logger.error(f"SandboxManager:cleanup error {e}",exc_info=True)
              self._stop_event.wait(self._cleanup_interval)
          logger.info(f"SandboxManager: cleaning up..... ")

      def _reap_expired(self):
          to_remove:List[Tuple[str,_SandboxEntry]] = []
          with self._global_lock:
              items=list(self._entries.items())

          if not items:
              logger.debug("SandboxManager:cleanup scen-no active sandboxex.")
              return


          for org_id,entry in items:
              with entry.lock:
                  idle=entry.idle_seconds
              remaining=self._idle_timeout - idle
              if remaining <= 0:
                  logger.info(
                      f"SandboxManager:[SCAN] org={org_id} idle={idle:.0f}s "
                      f"(>= threshold {self._idle_timeout}s) ->WILL RECLAIM"
                  )
                  to_remove.append((org_id,entry))
              else:
                  logger.debug(
                      f"SandboxManager:[SCAN] org={org_id} idle={idle:.0f}s ]"
                      f"(recycle in {remaining:.0f}s))"
                  )
          if not to_remove:
              logger.debug(
                  f"SandboxManager: cleanup scan complete - "
                  f"{len(items)} sandbox(es) active, 0 reclaimed."
              )
              return

          reclaimed=0
          for org_id,entry in to_remove:
              with self._global_lock:
                  cur=self._entries.get(org_id)
                  if cur is entry:
                      del self._entries[org_id]
                  else:
                      logger.warning(
                          f"SandboxManager:[SCAN] org={org_id} entry changed before "
                          f"reclamation ,skiping"
                      )
                      continue
              while entry.lock:
                  idle_val=entry.idle_seconds
                  entry.close()
              reclaimed+=1
              logger.info(
                  f"SandboxManager:[RECLAIMED] org={org_id}  ]"
                  f"(was idle in idle={idle_val:.0f}s)"
              )

          still_active=len(items)-reclaimed
          logger.info(
              f"SandboxManager: cleanup scan complete -"
              f"scanned={len(items)},reclaimed={reclaimed:.0f}s still_active={still_active}"
          )

      def get_backend(self,org_id:str):
          if not self._available:
              return  None

          with self._global_lock:
              entry=self._entries.get(org_id)
              if entry is None:
                  logger.info("SandboxManager creating new sandbox for org={org_id}")
                  sandbox=SandboxSync.create(self._image)
                  backend = OpensandboxBackend(sandbox=sandbox)
                  entry=_SandboxEntry(sandbox=sandbox,backend=backend)
                  self._entries[org_id]=entry
                  need_provision=True
              else:
                  logger.debug(f"SandboxManager reading existing sandbox for org={org_id}")
                  need_provision=False

          with entry.lock:
              entry.touch()
              backend=entry.backend

          if need_provision:
              t=threading.Thread(
                  target=self._provision_entry,
                  args=(org_id,entry),
                  name=f"Sandbox-Provision-{org_id}",
                  daemon=True
              )
              t.start()
          return backend