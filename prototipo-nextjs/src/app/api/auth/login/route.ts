import { compare } from "bcryptjs";
import { NextResponse } from "next/server";
import { createSession } from "@/lib/auth";
import { prisma } from "@/lib/prisma";

type LoginPayload = {
  email?: string;
  password?: string;
};

export async function POST(request: Request) {
  const body = (await request.json()) as LoginPayload;
  const email = body.email?.trim().toLowerCase();
  const password = body.password ?? "";

  if (!email || !password) {
    return NextResponse.json({ message: "Email y password son obligatorios." }, { status: 400 });
  }

  const user = await prisma.user.findUnique({
    where: { email }
  });

  if (!user) {
    return NextResponse.json({ message: "Credenciales invalidas." }, { status: 401 });
  }

  const ok = await compare(password, user.passwordHash);
  if (!ok) {
    return NextResponse.json({ message: "Credenciales invalidas." }, { status: 401 });
  }

  await createSession(user.id, user.role);

  return NextResponse.json({
    role: user.role,
    nextPath: user.role === "ADMIN" ? "/alcaldia" : user.role === "DRIVER" ? "/conductor" : "/colegio"
  });
}
