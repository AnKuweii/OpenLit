import { HealthCheck } from "./HealthCheck";

export function Header() {
  return (
    <header className="px-6 pt-6 pb-3 relative" style={{ border: 'none' }}>
      <div className="relative flex items-center justify-between">
        <div className="w-48"></div>

        <div className="text-center flex-1">
          <h1 className="text-3xl font-semibold tracking-tight" style={{ fontFamily: '"Inter", system-ui, sans-serif' }}>
            <span className="bg-gradient-to-r from-cyan-400 via-purple-500 to-fuchsia-500 bg-clip-text text-transparent" style={{ filter: 'drop-shadow(0 0 12px rgba(0,240,255,0.5)) drop-shadow(0 0 24px rgba(191,0,255,0.3))' }}>
              OpenLit
            </span>
          </h1>
        </div>

        <div className="w-48 flex justify-end items-center gap-3">
          <HealthCheck />
        </div>
      </div>
    </header>
  );
}
