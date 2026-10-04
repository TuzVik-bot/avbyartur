import { ImageResponse } from "next/og";
import { CornflowerMark } from "@/components/cornflower-mark";

export const size = { width: 512, height: 512 };
export const contentType = "image/png";

export default function Icon512() {
  return new ImageResponse(<CornflowerMark size={size.width} safeMargin={0.12} rounded={false} />, size);
}
