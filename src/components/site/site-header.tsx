"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { Menu, X } from "lucide-react";
import { BrandMark } from "./brand-mark";
import { TOOLS } from "@/lib/site";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function SiteHeader() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  return (
    <header className="sticky top-0 z-50 border-b border-border/70 bg-[#f4f7f8]/80 backdrop-blur-xl">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4 sm:px-6">
        <BrandMark size="sm" />
        <nav className="hidden items-center gap-1 md:flex" aria-label="Primary">
          {TOOLS.map((tool) => {
            const active = pathname === tool.href || pathname.startsWith(`${tool.href}/`);
            return (
              <Link
                key={tool.slug}
                href={tool.href}
                className={cn(
                  "rounded-full px-3.5 py-1.5 text-sm font-medium transition-colors",
                  active
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:bg-secondary hover:text-foreground",
                )}
              >
                {tool.short}
              </Link>
            );
          })}
          <Link
            href="/about"
            className={cn(
              "rounded-full px-3.5 py-1.5 text-sm font-medium transition-colors",
              pathname === "/about"
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:bg-secondary hover:text-foreground",
            )}
          >
            About
          </Link>
        </nav>
        <Button
          variant="ghost"
          size="icon"
          className="md:hidden"
          aria-label={open ? "Close menu" : "Open menu"}
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
        >
          {open ? <X /> : <Menu />}
        </Button>
      </div>
      {open ? (
        <div className="border-t border-border/70 bg-[#f4f7f8] px-4 py-3 md:hidden">
          <nav className="flex flex-col gap-1" aria-label="Mobile">
            {TOOLS.map((tool) => (
              <Link
                key={tool.slug}
                href={tool.href}
                onClick={() => setOpen(false)}
                className="rounded-lg px-3 py-2.5 text-sm font-medium text-foreground hover:bg-secondary"
              >
                {tool.name}
              </Link>
            ))}
            <Link
              href="/about"
              onClick={() => setOpen(false)}
              className="rounded-lg px-3 py-2.5 text-sm font-medium text-foreground hover:bg-secondary"
            >
              About
            </Link>
          </nav>
        </div>
      ) : null}
    </header>
  );
}
