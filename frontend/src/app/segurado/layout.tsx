import { PortalFrame } from "@/components/portal/segurado";

export const metadata = { title: "Portal do Segurado" };

export default function Layout({ children }: { children: React.ReactNode }) {
  return <PortalFrame>{children}</PortalFrame>;
}
