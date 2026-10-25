"use client";

import { usePathname } from "next/navigation";
import { useEffect } from "react";

export function PageTransition({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  useEffect(() => {
    delete document.documentElement.dataset.navigating;
  }, [pathname]);

  return (
    <div
      key={pathname}
      className="animate-[page-enter_360ms_cubic-bezier(0.22,1,0.36,1)_both]"
    >
      {children}
    </div>
  );
}
