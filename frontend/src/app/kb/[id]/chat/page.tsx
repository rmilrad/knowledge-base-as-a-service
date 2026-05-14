"use client";

import { useEffect } from "react";
import { useParams, useRouter } from "next/navigation";

// Chat is now an integrated panel on the KB detail page.
// Redirect any direct visits to /kb/[id]/chat back to /kb/[id].
export default function ChatRedirect() {
  const params = useParams();
  const router = useRouter();
  const id = params.id as string;

  useEffect(() => {
    router.replace(`/kb/${id}`);
  }, [router, id]);

  return null;
}
