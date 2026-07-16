"use client";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

export function useReviewHistory(workspaceId: string) {
  return useQuery({
    queryKey: ["review-history", workspaceId],
    queryFn:  () => api.getReviewHistory(workspaceId),
    enabled:  !!workspaceId,
  });
}

export function useMergeHistory(workspaceId: string) {
  return useQuery({
    queryKey: ["merge-history", workspaceId],
    queryFn:  () => api.getMergeHistory(workspaceId),
    enabled:  !!workspaceId,
  });
}

export function useDashboardStats() {
  return useQuery({
    queryKey: ["dashboard-stats"],
    queryFn:  () => api.getDashboardStats(),
    refetchInterval: 30_000,
    retry: false,
  });
}

export function useTeamUsage(workspaceId = "") {
  return useQuery({
    queryKey: ["team-usage", workspaceId],
    queryFn:  () => api.getTeamUsage(workspaceId),
    refetchInterval: 60_000,
    retry: false,
  });
}

export function useReport(reviewId: string) {
  return useQuery({
    queryKey: ["report", reviewId],
    queryFn:  () => api.getReport(reviewId),
    enabled:  !!reviewId,
  });
}
