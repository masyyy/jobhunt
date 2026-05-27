import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Copy, Mail, Trash2 } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { useAuth } from '@/hooks/use-auth'
import {
  queryKeys,
  fetchAdminUsers,
  createInvite,
  deleteAdminUser,
  reinviteAdminUser,
  type InviteResponse,
} from '@/lib/queries'

export default function AdminPage() {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const usersQuery = useQuery({
    queryKey: queryKeys.adminUsers(),
    queryFn: fetchAdminUsers,
  })

  const [email, setEmail] = useState('')
  const [lastInvite, setLastInvite] = useState<InviteResponse | null>(null)
  const [copied, setCopied] = useState(false)
  const [deletingId, setDeletingId] = useState<string | null>(null)

  const inviteMutation = useMutation({
    mutationFn: (email: string) => createInvite(email),
    onSuccess: (data) => {
      setLastInvite(data)
      setEmail('')
      setCopied(false)
      void queryClient.invalidateQueries({ queryKey: queryKeys.adminUsers() })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (userId: string) => deleteAdminUser(userId),
    onSettled: () => {
      setDeletingId(null)
      void queryClient.invalidateQueries({ queryKey: queryKeys.adminUsers() })
    },
  })

  const reinviteMutation = useMutation({
    mutationFn: (userId: string) => reinviteAdminUser(userId),
    onSuccess: (data) => {
      setLastInvite(data)
      setCopied(false)
    },
  })

  const handleDelete = (userId: string, userEmail: string) => {
    if (!window.confirm(`Delete ${userEmail}? This cannot be undone.`)) return
    setDeletingId(userId)
    deleteMutation.mutate(userId)
  }

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    inviteMutation.mutate(email)
  }

  const handleCopy = async () => {
    if (!lastInvite) return
    await navigator.clipboard.writeText(lastInvite.action_link)
    setCopied(true)
  }

  return (
    <div className="min-h-screen bg-background">
      <div className="mx-auto max-w-3xl px-4 py-8">
        <Link
          to="/"
          className="mb-6 inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" /> Back
        </Link>

        <h1 className="mb-6 text-2xl font-semibold">Admin</h1>

        <Card className="mb-6">
          <CardHeader>
            <CardTitle>Invite a user</CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="flex flex-col gap-4">
              <Input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="user@example.com"
                required
              />
              <Button type="submit" disabled={inviteMutation.isPending || !email}>
                {inviteMutation.isPending ? 'Generating...' : 'Generate invite'}
              </Button>
              {inviteMutation.error && (
                <p className="text-sm text-destructive">
                  {inviteMutation.error instanceof Error
                    ? inviteMutation.error.message
                    : 'Failed to create invite'}
                </p>
              )}
              {lastInvite && (
                <div className="flex flex-col gap-2 rounded-md border border-border p-3">
                  <p className="text-sm">
                    Invite link for <span className="font-mono">{lastInvite.email}</span>. Share it
                    manually — it expires in 24 hours.
                  </p>
                  {/* TODO(auth): PoC-only manual delivery. This Supabase action link grants
                      a session as the target account to whoever opens it. Replace this with
                      direct email delivery before adding customer admins or production data. */}
                  <Textarea readOnly value={lastInvite.action_link} className="font-mono text-xs" />
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => void handleCopy()}
                  >
                    <Copy className="mr-2 h-4 w-4" />
                    {copied ? 'Copied' : 'Copy link'}
                  </Button>
                </div>
              )}
            </form>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Users</CardTitle>
          </CardHeader>
          <CardContent>
            {usersQuery.isLoading && <p className="text-sm text-muted-foreground">Loading...</p>}
            {usersQuery.error && <p className="text-sm text-destructive">Failed to load users</p>}
            {usersQuery.data && (
              <>
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border text-left text-muted-foreground">
                      <th className="py-2 pr-4 font-medium">Email</th>
                      <th className="py-2 pr-4 font-medium">Role</th>
                      <th className="py-2 pr-4 font-medium">Joined</th>
                      <th className="py-2 font-medium w-20" />
                    </tr>
                  </thead>
                  <tbody>
                    {usersQuery.data.map((u) => {
                      const isSelf = u.id === user?.id
                      const isDeleting = deletingId === u.id
                      return (
                        <tr key={u.id} className="border-b border-border last:border-0">
                          <td className="py-2 pr-4">{u.email}</td>
                          <td className="py-2 pr-4">{u.role}</td>
                          <td className="py-2 pr-4 text-muted-foreground">
                            {new Date(u.created_at).toLocaleDateString()}
                          </td>
                          <td className="py-2">
                            <div className="flex items-center justify-end gap-1">
                              <Button
                                type="button"
                                variant="ghost"
                                size="icon"
                                disabled={
                                  reinviteMutation.isPending && reinviteMutation.variables === u.id
                                }
                                title="Send a fresh invite link (e.g. forgot password, link expired)"
                                onClick={() => reinviteMutation.mutate(u.id)}
                              >
                                <Mail className="h-4 w-4 text-muted-foreground" />
                              </Button>
                              <Button
                                type="button"
                                variant="ghost"
                                size="icon"
                                disabled={isSelf || isDeleting}
                                title={isSelf ? 'Cannot delete your own account' : 'Delete user'}
                                onClick={() => handleDelete(u.id, u.email)}
                              >
                                <Trash2 className="h-4 w-4 text-muted-foreground" />
                              </Button>
                            </div>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
                {deleteMutation.error && (
                  <p className="mt-3 text-sm text-destructive">
                    {deleteMutation.error instanceof Error
                      ? deleteMutation.error.message
                      : 'Failed to delete user'}
                  </p>
                )}
                {reinviteMutation.error && (
                  <p className="mt-3 text-sm text-destructive">
                    {reinviteMutation.error instanceof Error
                      ? reinviteMutation.error.message
                      : 'Failed to generate invite link'}
                  </p>
                )}
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
