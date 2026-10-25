// Small inline icon set (Lucide-style strokes) so the app has no icon dependency.
type IconProps = { size?: number; className?: string };

function svg(path: React.ReactNode, { size = 16, className }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}
      strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      {path}
    </svg>
  );
}

export const PlusIcon = (p: IconProps) => svg(<path d="M12 5v14M5 12h14" />, p);
export const RefreshIcon = (p: IconProps) =>
  svg(<><path d="M21 12a9 9 0 1 1-2.64-6.36" /><path d="M21 3v6h-6" /></>, p);
export const TrashIcon = (p: IconProps) =>
  svg(<><path d="M3 6h18" /><path d="M8 6V4h8v2" /><path d="M19 6l-1 14H6L5 6" /></>, p);
export const DownloadIcon = (p: IconProps) =>
  svg(<><path d="M12 3v12" /><path d="m7 10 5 5 5-5" /><path d="M5 21h14" /></>, p);
export const FileIcon = (p: IconProps) =>
  svg(<><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5" /></>, p);
export const CheckIcon = (p: IconProps) => svg(<path d="m5 12 5 5L20 7" />, p);
export const AlertIcon = (p: IconProps) =>
  svg(<><circle cx="12" cy="12" r="9" /><path d="M12 8v4M12 16h.01" /></>, p);
export const ClockIcon = (p: IconProps) =>
  svg(<><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>, p);
export const LockIcon = (p: IconProps) =>
  svg(<><rect x="5" y="11" width="14" height="10" rx="2" /><path d="M8 11V8a4 4 0 0 1 8 0v3" /></>, p);
export const ExternalIcon = (p: IconProps) =>
  svg(<><path d="M14 4h6v6" /><path d="M20 4 10 14" /><path d="M19 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h5" /></>, p);
export const XIcon = (p: IconProps) => svg(<path d="M6 6l12 12M18 6 6 18" />, p);
export const LayersIcon = (p: IconProps) =>
  svg(<><path d="m12 3 9 5-9 5-9-5z" /><path d="m3 13 9 5 9-5" /></>, p);
export const Spinner = ({ size = 14 }: IconProps) => (
  <span className="spinner" style={{ width: size, height: size }} aria-hidden="true" />
);
