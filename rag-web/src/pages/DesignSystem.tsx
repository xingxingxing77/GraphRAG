/**
 * DesignSystemPage（06 §7，dev-only）：BUI 组件预览与目视验收载体。
 * 生产构建剔除（思路同 SYS_403_DEBUG_DISABLED）；10.7 单元五批次落地。
 */
export default function DesignSystemPage() {
  return (
    <div className="mx-auto max-w-3xl p-6">
      <h1 className="mb-4 text-lg font-semibold">设计系统（dev-only）</h1>
      <p className="text-sm text-neutral-500">
        Beautiful UI 20 组件预览占位（单元 10.7，前端设计系统落地方案 §5 批次执行）。
      </p>
    </div>
  );
}
