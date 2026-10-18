# sync.spin — 原子自旋锁

基于顺序一致原子内建和 `pause` 提示的自旋锁，锁状态为一个 `u32` 单元。没有中断、抢占或调度器集成。

## 接口

```text
pub struct Lock { pub state:u32 }
pub unsafe fn try_lock(lock:*Lock) bool
pub unsafe fn lock(lock:*Lock) void
pub unsafe fn unlock(lock:*Lock) void
```

## 语义与契约

- `Lock` 由调用方以 `Lock { state: 0 }` 初始化：`0` 表示未持有，`1` 表示持有。初始化必须在发布给其他线程之前完成，之后 `state` 只能通过原子内建访问。
- `try_lock` 用强 CAS 执行 `0 -> 1` 并据返回旧值判断成功，不等待。
- `lock` 失败时用原子读取加 `asm { pause }` 等待，直到取得锁。
- `unlock` 用 `atomic_store` 写 `0`。

## 必须遵守的前置条件

- 不得重复加锁；只有持有者可以解锁。
- `state` 公开仅为当前无构造器语言提供初始化途径，**不允许并发普通读写它**。
- 同核中断重入、抢占，或持有者无法运行，都可能死锁；这些由调用者管理。本锁无递归、无调度器依赖。

## 用法示例

```text
import sync.spin as spin;
var lock = spin.Lock { state: 0 };
unsafe {
    spin.lock(&lock);
    // 临界区
    spin.unlock(&lock);
}
```

## 已验证

宿主测试用原生线程（Windows）或 pthread（Linux）建立四线程竞争，临界区更新普通共享计数；核对最终值、`try_lock` 成功/失败与释放后再次获得，测试带超时，两种模式均通过。
