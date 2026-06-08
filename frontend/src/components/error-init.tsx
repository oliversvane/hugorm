"use client";
import { useEffect } from "react";
import { installErrorReporter } from "@/lib/error-reporter";

export function ErrorInit() {
  useEffect(() => {
    installErrorReporter();
  }, []);
  return null;
}
