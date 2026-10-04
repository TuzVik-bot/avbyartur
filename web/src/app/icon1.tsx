import { ImageResponse } from "next/og";
import { CornflowerMark } from "@/components/cornflower-mark";

export const size = { width: 192, height: 192 };
export const contentType = "image/png";

export default function Icon192() {
  return new ImageResponse(<CornflowerMark size={size.width} safeMargin={0.08} rounded={false} />, size);
}
