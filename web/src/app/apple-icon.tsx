import { ImageResponse } from "next/og";
import { CornflowerMark } from "@/components/cornflower-mark";

export const size = { width: 180, height: 180 };
export const contentType = "image/png";

export default function AppleIcon() {
  return new ImageResponse(<CornflowerMark size={size.width} safeMargin={0.08} rounded={false} />, size);
}
